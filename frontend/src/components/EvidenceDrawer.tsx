import { ArrowRight, X } from 'lucide-react';
import { useEffect } from 'react';
import { agentName } from '../mock/meta';
import type { AgentId, CaseFile, Verdict } from '../mock/types';
import { AGENT_ICON } from './icons';

const TONE: Record<Verdict, string> = { supports: 'support', contradicts: 'against', inconclusive: 'neutral' };

/** Side sheet with what one agent found, round by round. Opens when a lane on the rail is clicked. */
export function EvidenceDrawer({ c, agent, t, onClose, onOpenSteps }: { c: CaseFile; agent: AgentId; t: number; onClose: () => void; onOpenSteps: () => void }) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [onClose]);
  const Icon = AGENT_ICON[agent];
  const runs = c.runs.filter((r) => r.agent === agent && r.at <= t);
  const first = runs[0];
  const latest = runs[runs.length - 1];
  const tone = latest ? TONE[latest.verdict] : 'neutral';
  return (
    <aside className="evidence-drawer" aria-label={`${agentName(agent)} evidence`}>
      <div className="drawer-handle" />
      <div className="drawer-head">
        <div className={`agent-icon large tone-${tone}`}>
          <Icon size={20} strokeWidth={1.7} />
        </div>
        <div>
          <span className="eyebrow">Agent evidence</span>
          <h3>{agentName(agent)}</h3>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close evidence">
          <X size={16} />
        </button>
      </div>
      {!first ? (
        <p className="drawer-wait">This agent has not started yet.</p>
      ) : (
        <>
          <div className="finding-block">
            <span className={`finding-dot tone-${TONE[first.verdict]}`} />
            <div>
              <strong>{t >= first.at + first.dur ? first.finding : 'Still searching…'}</strong>
              <p>{first.question}</p>
              {first.gaps?.map((g) => (
                <p key={g}>{g}</p>
              ))}
            </div>
          </div>
          {runs.slice(1).map((r) => (
            <div className="finding-block second" key={r.id}>
              <span className={`finding-dot tone-${TONE[r.verdict]}`} />
              <div>
                <span className="eyebrow">Focused second pass</span>
                <strong>{t >= r.at + r.dur ? r.finding : 'Checking again…'}</strong>
                <p>{r.question}</p>
              </div>
            </div>
          ))}
        </>
      )}
      <button type="button" className="text-button" onClick={onOpenSteps}>
        Open the full trail <ArrowRight size={14} />
      </button>
    </aside>
  );
}
