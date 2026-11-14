import { Check, MessageSquarePlus, Send } from 'lucide-react';
import { useState } from 'react';
import { agentName, OUTCOMES } from '../lib/meta';
import type { Decision, Outcome, Question } from '../lib/types';

const REASONS = ['New information from the claimant', 'Evidence source not reliable', 'Site visit already done', 'Policy exception applies'];

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
            {decision.kind === 'approve' ? 'Recommendation approved' : 'Recommendation overridden'}: {OUTCOMES[decision.outcome].action.toLowerCase()}
          </p>
          <p>
            Logged {decision.at}.{decision.reason ? ` Reason: ${decision.reason}.` : ''}
          </p>
        </div>
      </div>
    );
  }

  if (!ready || !recommended) {
    return (
      <div className="decision is-waiting">
        <p className="decision-title">Your decision opens when the verdict is in</p>
        <p>The system only recommends. Nothing is paid or refused until you decide.</p>
      </div>
    );
  }

  const rec = OUTCOMES[recommended];
  const others = (Object.keys(OUTCOMES) as Outcome[]).filter((r) => r !== recommended);

  return (
    <div className="decision">
      <div className="decision-rec">
        <p className="eyebrow">Recommended next step</p>
        <p className="decision-title">{rec.action}</p>
        <p>{rec.desc}</p>
      </div>
      <div className="decision-actions">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onApprove}>
          <Check size={15} strokeWidth={2.6} />
          Approve recommendation
        </button>
        <button type="button" className={`btn btn-secondary${mode === 'override' ? ' is-on' : ''}`} aria-expanded={mode === 'override'} onClick={() => setMode(mode === 'override' ? 'idle' : 'override')}>
          Choose another route
        </button>
        <button type="button" className={`btn btn-secondary${mode === 'ask' ? ' is-on' : ''}`} aria-expanded={mode === 'ask'} onClick={() => setMode(mode === 'ask' ? 'idle' : 'ask')}>
          <MessageSquarePlus size={15} />
          Ask for more
        </button>
      </div>

      {mode === 'override' && (
        <div className="decision-more">
          <div className="route-options" role="radiogroup" aria-label="Route">
            {others.map((r) => (
              <button type="button" key={r} role="radio" aria-checked={outcome === r} className={`route-option${outcome === r ? ' is-on' : ''}`} onClick={() => { setOutcome(r); setError(''); }}>
                <b>{OUTCOMES[r].action}</b>
                <span>{OUTCOMES[r].desc}</span>
              </button>
            ))}
          </div>
          <p className="field-label">Why are you overriding?</p>
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
              if (!outcome) return setError('Pick a route first');
              if (!reason) return setError('Pick a reason. Overrides are logged with one.');
              onOverride(outcome, reason);
              setMode('idle');
            }}
          >
            Confirm override
          </button>
        </div>
      )}

      {mode === 'ask' && (
        <form
          className="decision-more"
          onSubmit={(e) => {
            e.preventDefault();
            if (!question.trim()) return setError('Write the question first');
            onAsk(question.trim());
            setQuestion('');
            setError('');
            setMode('idle');
          }}
        >
          <label className="field-label" htmlFor="ask-q">
            What should the agents look into?
          </label>
          <div className="ask-row">
            <input id="ask-q" value={question} placeholder="Were gusts above 70 km/h on the next day too?" onChange={(e) => { setQuestion(e.target.value); setError(''); }} />
            <button type="submit" className="btn btn-primary" disabled={busy}>
              <Send size={14} />
              Send to orchestrator
            </button>
          </div>
          <p className="card-note">This starts one more round of agents. The score and the recommendation can change.</p>
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
                Round {q.round}
                {q.agent ? ` · ${agentName(q.agent)}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
