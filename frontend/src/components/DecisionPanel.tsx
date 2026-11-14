import { Check, MessageSquarePlus, Send } from 'lucide-react';
import { useState } from 'react';
import { agentName, OUTCOMES } from '../lib/meta';
import type { Decision, Outcome, Question } from '../lib/types';

const REASONS = ['Informații noi de la asigurat', 'Sursă de dovezi nesigură', 'Inspecția a fost deja făcută', 'Se aplică o excepție din poliță'];

interface Props {
  ready: boolean;
  recommended?: Outcome;
  decision?: Decision;
  questions: Question[];
  busy: boolean;
  /** POST /claims/{id}/decision with decision "approve". */
  onApprove: () => void;
  /** POST /claims/{id}/decision with decision "modify": another outcome, with a reason. */
  onOverride: (outcome: Outcome, reason: string) => void;
  /** POST /claims/{id}/question: one more round of agents on the adjuster's question. */
  onAsk: (question: string) => void;
}

export function DecisionPanel({ ready, recommended, decision, questions, busy, onApprove, onOverride, onAsk }: Props) {
  const [mode, setMode] = useState<'idle' | 'override' | 'ask'>('idle');
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [reason, setReason] = useState('');
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');

  if (decision) {
    return (
      <div className="decision is-done" role="status">
        <span className="decision-check">
          <Check size={18} strokeWidth={3} />
        </span>
        <div>
          <p className="decision-title">
            {decision.kind === 'approve' ? 'Ați aprobat recomandarea' : 'Ați modificat recomandarea'}: {OUTCOMES[decision.outcome].action.toLowerCase()}
          </p>
          <p>
            Înregistrat {decision.at}.{decision.reason ? ` Motiv: ${decision.reason}.` : ''}
          </p>
        </div>
      </div>
    );
  }

  if (!ready || !recommended) {
    return (
      <div className="decision is-waiting">
        <p className="decision-title">Puteți decide după verdict</p>
        <p>Sistemul doar recomandă. Nimic nu se plătește și nu se respinge fără decizia dumneavoastră.</p>
      </div>
    );
  }

  const rec = OUTCOMES[recommended];
  const others = (Object.keys(OUTCOMES) as Outcome[]).filter((r) => r !== recommended);

  return (
    <div className="decision">
      <div className="decision-rec">
        <p className="eyebrow">Recomandare</p>
        <p className="decision-title">{rec.action}</p>
        <p>{rec.desc}</p>
      </div>
      <div className="decision-actions">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onApprove}>
          <Check size={15} strokeWidth={2.6} />
          Aprobați recomandarea
        </button>
        <button type="button" className={`btn btn-secondary${mode === 'override' ? ' is-on' : ''}`} aria-expanded={mode === 'override'} onClick={() => setMode(mode === 'override' ? 'idle' : 'override')}>
          Alegeți altă soluție
        </button>
        <button type="button" className={`btn btn-secondary${mode === 'ask' ? ' is-on' : ''}`} aria-expanded={mode === 'ask'} onClick={() => setMode(mode === 'ask' ? 'idle' : 'ask')}>
          <MessageSquarePlus size={15} />
          Cereți verificări suplimentare
        </button>
      </div>

      {mode === 'override' && (
        <div className="decision-more">
          <div className="route-options" role="radiogroup" aria-label="Soluție">
            {others.map((r) => (
              <button type="button" key={r} role="radio" aria-checked={outcome === r} className={`route-option${outcome === r ? ' is-on' : ''}`} onClick={() => { setOutcome(r); setError(''); }}>
                <b>{OUTCOMES[r].action}</b>
                <span>{OUTCOMES[r].desc}</span>
              </button>
            ))}
          </div>
          <p className="field-label">De ce schimbați recomandarea?</p>
          <div className="reason-chips">
            {REASONS.map((x) => (
              <button type="button" key={x} className={`chip is-button${reason === x ? ' is-on' : ''}`} aria-pressed={reason === x} onClick={() => { setReason(x); setError(''); }}>
                {x}
              </button>
            ))}
          </div>
          {error && <p className="form-error">{error}</p>}
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => {
              if (!outcome) return setError('Alegeți mai întâi o soluție.');
              if (!reason) return setError('Alegeți un motiv. Orice schimbare se înregistrează cu motivul ei.');
              onOverride(outcome, reason);
              setMode('idle');
            }}
          >
            Confirmați schimbarea
          </button>
        </div>
      )}

      {mode === 'ask' && (
        <form
          className="decision-more"
          onSubmit={(e) => {
            e.preventDefault();
            if (!question.trim()) return setError('Scrieți mai întâi întrebarea.');
            onAsk(question.trim());
            setQuestion('');
            setError('');
            setMode('idle');
          }}
        >
          <label className="field-label" htmlFor="ask-q">
            Ce doriți să mai verifice agenții?
          </label>
          <div className="ask-row">
            <input id="ask-q" value={question} placeholder="Au fost rafale de peste 70 km/h și a doua zi?" onChange={(e) => { setQuestion(e.target.value); setError(''); }} />
            <button type="submit" className="btn btn-primary" disabled={busy}>
              <Send size={14} />
              Trimiteți
            </button>
          </div>
          <p className="card-note">Agenții vor face încă o rundă de verificări, așa că scorul și recomandarea se pot schimba.</p>
          {error && <p className="form-error">{error}</p>}
        </form>
      )}

      {questions.length > 0 && (
        <ul className="requests">
          {questions.map((q) => (
            <li key={`${q.round}-${q.text}`}>
              <span className="pulse-dot" />
              <span>{q.text}</span>
              <span className="chip">
                Runda {q.round}
                {q.agent ? ` · ${agentName(q.agent)}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
