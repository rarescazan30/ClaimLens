import { ChevronDown, EyeOff, RotateCcw, Scale, Workflow } from 'lucide-react';
import { fmtClock } from '../lib/derive';
import { bandOf, computeScore } from '../lib/score';
import { agentName, BANDS, ROUTES } from '../mock/meta';
import type { CaseFile, Evidence, Route } from '../mock/types';
import { Aurora, type Tone } from './Aurora';
import { MapCard, ScoreMeter } from './Cards';
import { AGENT_ICON } from './icons';
import { PhotoGrid } from './ui';

interface Props {
  c: CaseFile;
  evidence: Evidence[];
  dismissed: string[];
  score: number;
  route: Route;
  gateTripped: boolean;
  tone: Tone;
  onToggle: (id: string) => void;
  onJump: (t: number) => void;
  children: React.ReactNode;
}

export function Report({ c, evidence, dismissed, score, route, gateTripped, tone, onToggle, onJump, children }: Props) {
  const band = bandOf(score);
  const live = evidence.filter((e) => !dismissed.includes(e.id));

  // Effect of each finding in score points: what the score would be without it.
  const rows = evidence
    .map((e) => {
      const off = dismissed.includes(e.id);
      const delta = off ? computeScore(c.p0, [...live, e]) - score : score - computeScore(c.p0, live.filter((x) => x.id !== e.id));
      return { e, off, delta };
    })
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const max = Math.max(10, ...rows.map((r) => Math.abs(r.delta)));
  const agentsHeard = new Set(live.map((e) => e.agent)).size;

  const flaggedPhotos = c.photos.filter((ph) => ph.states[ph.states.length - 1].status === 'fail').length;

  const steps = [
    { at: c.windows.find((w) => w.stage === 'plan')!.at, icon: Workflow, who: 'Orchestrator', text: `Set ${c.plan.hypotheses.length} hypotheses and dispatched ${c.plan.dispatch.filter((d) => !d.skipped).length} of 6 agents.` },
    ...c.judge.map((j) => ({ at: j.at, icon: Scale, who: `Judge, round ${j.round}`, text: j.summary })),
  ];

  return (
    <div className="report">
      <section className={`card verdict-hero b-${band}`}>
        <Aurora x={0.12} y={0.5} spread={0.9} tone={tone} gain={0.9} />
        <div className="verdict-main">
          <p className="eyebrow">Verdict · {c.id}</p>
          <div className="verdict-score">
            <span className="score-num is-xl">{score}</span>
            <div>
              <h2>{BANDS[band].label}</h2>
              <p className="verdict-route">
                Recommended: <b>{ROUTES[route].action.toLowerCase()}</b>
              </p>
            </div>
          </div>
          <p className="verdict-why">{c.rationale}</p>
          <ScoreMeter score={score} />
        </div>
        <div className="verdict-side">{children}</div>
      </section>

      <div className="report-grid">
        <section className="card contrib">
          <header className="card-head">
            <div>
              <h3>What moved the score</h3>
              <p className="card-sub">Points each finding adds or removes. Set one aside to see the score without it.</p>
            </div>
            <span className="chip">Starts at {Math.round(c.p0 * 100)}</span>
          </header>
          <div className="contrib-axis" aria-hidden="true">
            <span />
            <span className="axis-labels">
              <i>Against the claim</i>
              <i>For the claim</i>
            </span>
          </div>
          <ul className="contrib-rows">
            {rows.map(({ e, off, delta }) => {
              const Icon = AGENT_ICON[e.agent];
              const w = (Math.abs(delta) / max) * 50;
              const sign = delta > 0 ? 'pos' : delta < 0 ? 'neg' : 'zero';
              return (
                <li key={e.id} className={`contrib-row is-${sign}${off ? ' is-off' : ''}`}>
                  <div className="contrib-what">
                    <span className="agent-ico">
                      <Icon size={15} />
                    </span>
                    <div>
                      <p className="contrib-title">{e.title}</p>
                      <p className="contrib-src">
                        <b>{e.value}</b> · {agentName(e.agent)}
                        {e.round > 1 ? `, round ${e.round}` : ''} · {e.source}
                      </p>
                    </div>
                  </div>
                  <div className="contrib-bar" role="img" aria-label={`${delta > 0 ? 'Adds' : delta < 0 ? 'Removes' : 'No effect:'} ${Math.abs(delta)} points`}>
                    <span className="contrib-zero" />
                    {sign !== 'zero' && <span className="contrib-fill" style={{ width: `${w}%`, [delta > 0 ? 'left' : 'right']: '50%' }} />}
                  </div>
                  <span className="contrib-delta">{off ? 'Set aside' : delta === 0 ? 'No effect' : `${delta > 0 ? '+' : '−'}${Math.abs(delta)}`}</span>
                  <button type="button" className="icon-btn" onClick={() => onToggle(e.id)} aria-label={off ? `Restore finding: ${e.title}` : `Set aside finding: ${e.title}`} title={off ? 'Restore this finding' : 'Set this finding aside'}>
                    {off ? <RotateCcw size={14} /> : <EyeOff size={14} />}
                  </button>
                </li>
              );
            })}
          </ul>
          <footer className="contrib-foot">
            <span>
              {live.length} of {evidence.length} findings counted, from {agentsHeard} agents · weights from {c.profile}
            </span>
          </footer>
        </section>

        <div className="report-side">
          <section className="card">
            <header className="card-head">
              <h3>Hard gates</h3>
            </header>
            <ul className="gates is-large">
              <li className="g-passed">
                <span className="gate-dot" />
                <div>
                  Coverage and conditions
                  <span>Policy active, peril covered, notified in time</span>
                </div>
                <b>Passed</b>
              </li>
              <li className={gateTripped ? 'g-flagged' : 'g-passed'}>
                <span className="gate-dot" />
                <div>
                  Evidence authenticity
                  <span>{gateTripped ? c.gate!.label : 'All photos verified on-site, after the event'}</span>
                </div>
                <b>{gateTripped ? 'Flagged' : 'Passed'}</b>
              </li>
            </ul>
            <p className="card-note">A flagged gate sends the case to a person, whatever the score says.</p>
          </section>

          <details className="card fold">
            <summary>
              <h3>How the verdict was reached</h3>
              <span className="chip">{steps.length} decisions</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <ol className="reason-steps">
              {steps.map((s) => (
                <li key={s.at}>
                  <button type="button" onClick={() => onJump(s.at)} title="Jump to this moment in the replay">
                    <span className="agent-ico">
                      <s.icon size={14} />
                    </span>
                    <span>
                      <b>{s.who}</b>
                      {s.text}
                    </span>
                    <span className="mono-value">{fmtClock(s.at)}</span>
                  </button>
                </li>
              ))}
            </ol>
          </details>

          <details className="card fold" open={flaggedPhotos > 0}>
            <summary>
              <h3>Claimant photos</h3>
              <span className={`chip${flaggedPhotos ? ' v-contradicts' : ''}`}>{flaggedPhotos ? `${flaggedPhotos} of ${c.photos.length} flagged` : `${c.photos.length} verified`}</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <PhotoGrid photos={c.photos} t={c.duration} />
          </details>

          <details className="card fold">
            <summary>
              <h3>Map</h3>
              <span className="chip">{c.place}</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <MapCard c={c} t={c.duration} />
          </details>
        </div>
      </div>
    </div>
  );
}
