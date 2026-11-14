import { Check, MessageSquarePlus, Send, Undo2 } from 'lucide-react';
import { useState } from 'react';
import type { Decision } from '../lib/hooks';
import { ROUTES } from '../mock/meta';
import type { Route } from '../mock/types';

const REASONS = ['New information from the claimant', 'Evidence source not reliable', 'Site visit already done', 'Policy exception applies'];

interface Props {
  ready: boolean;
  recommended: Route;
  decision?: Decision;
  requests: string[];
  onDecide: (d: Decision | undefined) => void;
  onAsk: (q: string) => void;
}

const now = () => new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

export function DecisionPanel({ ready, recommended, decision, requests, onDecide, onAsk }: Props) {
  const [mode, setMode] = useState<'idle' | 'override' | 'ask'>('idle');
  const [route, setRoute] = useState<Route | null>(null);
  const [reason, setReason] = useState('');
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');
  const rec = ROUTES[recommended];

  if (!ready) {
    return (
      <div className="decision is-waiting">
        <p className="decision-title">Your decision opens when the verdict is in</p>
        <p>The system only recommends. Nothing is paid or refused until you decide.</p>
      </div>
    );
  }

  if (decision) {
    return (
      <div className="decision is-done" role="status">
        <span className="decision-check">
          <Check size={18} strokeWidth={3} />
        </span>
        <div>
          <p className="decision-title">
            {decision.kind === 'approved' ? 'Recommendation approved' : 'Recommendation overridden'}: {ROUTES[decision.route].action.toLowerCase()}
          </p>
          <p>
            Logged at {decision.at} by Ana M.
            {decision.reason ? ` Reason: ${decision.reason.toLowerCase()}.` : ''}
          </p>
        </div>
        <button type="button" className="btn btn-quiet" onClick={() => onDecide(undefined)}>
          <Undo2 size={14} />
          Undo
        </button>
      </div>
    );
  }

  const others = (Object.keys(ROUTES) as Route[]).filter((r) => r !== recommended);

  return (
    <div className="decision">
      <div className="decision-rec">
        <p className="eyebrow">Recommended next step</p>
        <p className="decision-title">{rec.action}</p>
        <p>{rec.desc}</p>
      </div>
      <div className="decision-actions">
        <button type="button" className="btn btn-primary" onClick={() => onDecide({ route: recommended, kind: 'approved', at: now() })}>
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
              <button type="button" key={r} role="radio" aria-checked={route === r} className={`route-option${route === r ? ' is-on' : ''}`} onClick={() => { setRoute(r); setError(''); }}>
                <b>{ROUTES[r].action}</b>
                <span>{ROUTES[r].desc}</span>
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
            onClick={() => {
              if (!route) return setError('Pick a route first');
              if (!reason) return setError('Pick a reason. Overrides are logged with one.');
              onDecide({ route, kind: 'overridden', reason, at: now() });
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
          }}
        >
          <label className="field-label" htmlFor="ask-q">
            What should the agents look into?
          </label>
          <div className="ask-row">
            <input id="ask-q" value={question} placeholder="Check whether neighbours on the same street filed claims" onChange={(e) => { setQuestion(e.target.value); setError(''); }} />
            <button type="submit" className="btn btn-primary">
              <Send size={14} />
              Send to orchestrator
            </button>
          </div>
          {error && <p className="form-error">{error}</p>}
        </form>
      )}

      {requests.length > 0 && (
        <ul className="requests">
          {requests.map((q) => (
            <li key={q}>
              <span className="pulse-dot" />
              <span>{q}</span>
              <span className="chip">Queued for the orchestrator</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
