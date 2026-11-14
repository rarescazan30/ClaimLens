import { ChevronDown, EyeOff, Scale, UserRound, Workflow } from 'lucide-react';
import { useState } from 'react';
import { fmtClock } from '../lib/derive';
import { contributionTitle, stepName } from '../lib/early';
import { agentName, AGENTS, BANDS, isAgent, OUTCOMES } from '../lib/meta';
import { baseOf, fmtScore, pointsOf } from '../lib/score';
import type { CaseFile, Evidence, ScoreStep } from '../lib/types';
import { Aurora, type Tone } from './Aurora';
import { MapCard, ScoreMeter } from './Cards';
import { AGENT_ICON } from './icons';
import { PhotoGrid } from './ui';

interface Props {
  c: CaseFile;
  /** The final score, as the backend computed it. */
  score: ScoreStep;
  tone: Tone;
  busy: boolean;
  /** Set a finding aside (POST /claims/{id}/evidence/{evidenceId}/reject). The backend cannot restore it. */
  onReject: (evidenceId: number) => void;
  onJump: (t: number) => void;
  children: React.ReactNode;
}

export function Report({ c, score, tone, busy, onReject, onJump, children }: Props) {
  const [arming, setArming] = useState<number | null>(null);
  const gateTripped = score.gates.find((g) => g.kind === 'clear_fake');
  const coverageGate = score.gates.find((g) => g.kind === 'coverage');

  // One row per finding the backend counted (its latest answer from each agent), plus the ones set aside.
  const counted = score.contributions
    .filter((k) => isAgent(k.agent))
    .map((k) => ({ k, e: c.evidence.find((e) => e.agent === k.agent && e.round === k.round && !e.rejected) }))
    .filter((x): x is { k: (typeof score.contributions)[number]; e: Evidence } => !!x.e)
    .map(({ k, e }) => ({ e, off: false, delta: pointsOf(score.score, k.delta_logit) }));
  // Client-data lines carry their own reason; they are counted in the score but are not findings that can be set aside.
  const clientLines = score.contributions
    .filter((k) => k.agent === 'client')
    .map((k) => ({ title: contributionTitle(k), delta: pointsOf(score.score, k.delta_logit) }));
  const context = score.contributions.find((k) => k.agent === 'context' && k.delta_logit !== 0);
  const aside = c.evidence.filter((e) => e.rejected).map((e) => ({ e, off: true, delta: 0 }));
  const rows = [...counted.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)), ...aside];
  const max = Math.max(10, ...rows.map((r) => Math.abs(r.delta)), ...clientLines.map((l) => Math.abs(l.delta)));

  const flaggedPhotos = c.photos.filter((ph) => ph.status === 'fail').length;
  const planWindow = c.windows.find((w) => w.stage === 'plan');
  const steps = [
    ...(planWindow
      ? [{ at: planWindow.at, icon: Workflow, who: 'Orchestrator', text: `Set ${c.plan.hypotheses.length} hypotheses and dispatched ${c.plan.dispatch.filter((d) => !d.skipped).length} of ${AGENTS.length} agents.` }]
      : []),
    ...c.judge.map((j) => ({ at: j.at, icon: Scale, who: `Judge, round ${j.round}`, text: j.summary })),
  ];

  return (
    <div className="report">
      <section className={`card verdict-hero b-${score.band}`}>
        <Aurora x={0.12} y={0.5} spread={0.9} tone={tone} gain={0.9} />
        <div className="verdict-main">
          <p className="eyebrow">Verdict · {c.id}</p>
          <div className="verdict-score">
            <span className="score-num is-xl">{fmtScore(score.score)}</span>
            <div>
              <h2>{BANDS[score.band].label}</h2>
              <p className="verdict-route">
                Recommended: <b>{OUTCOMES[score.recommendation].action.toLowerCase()}</b>
              </p>
            </div>
          </div>
          {c.rationale && <p className="verdict-why">{c.rationale}</p>}
          <ScoreMeter score={score.score} band={score.band} />
        </div>
        <div className="verdict-side">{children}</div>
      </section>

      <div className="report-grid">
        <section className="card contrib">
          <header className="card-head">
            <div>
              <h3>What moved the score</h3>
              <p className="card-sub">Points each finding adds or removes. Setting one aside recomputes the score without it and cannot be undone.</p>
            </div>
            <span className="chip">Starts at {baseOf(score)}</span>
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
                        <b>{agentName(e.agent)}</b>
                        {e.round > 1 ? `, round ${e.round}` : ''} · {e.source}
                      </p>
                      {e.detail && <p className="contrib-src">{e.detail}</p>}
                    </div>
                  </div>
                  <div className="contrib-bar" role="img" aria-label={`${delta > 0 ? 'Adds' : delta < 0 ? 'Removes' : 'No effect:'} ${Math.abs(delta)} points`}>
                    <span className="contrib-zero" />
                    {sign !== 'zero' && <span className="contrib-fill" style={{ width: `${w}%`, [delta > 0 ? 'left' : 'right']: '50%' }} />}
                  </div>
                  <span className="contrib-delta">{off ? 'Set aside' : delta === 0 ? 'No effect' : `${delta > 0 ? '+' : '−'}${Math.abs(delta)}`}</span>
                  {off || c.decision ? (
                    <span className="contrib-spacer" />
                  ) : arming === e.id ? (
                    <button type="button" className="btn btn-quiet contrib-confirm" disabled={busy} onClick={() => { setArming(null); onReject(e.id); }} onBlur={() => setArming(null)}>
                      Confirm
                    </button>
                  ) : (
                    <button type="button" className="icon-btn" onClick={() => setArming(e.id)} aria-label={`Set aside finding: ${e.title}`} title="Set this finding aside (cannot be undone)">
                      <EyeOff size={14} />
                    </button>
                  )}
                </li>
              );
            })}
            {clientLines.map((l, i) => {
              const sign = l.delta > 0 ? 'pos' : l.delta < 0 ? 'neg' : 'zero';
              return (
                <li key={`client-${i}`} className={`contrib-row is-${sign}`}>
                  <div className="contrib-what">
                    <span className="agent-ico">
                      <UserRound size={15} />
                    </span>
                    <div>
                      <p className="contrib-title">{l.title}</p>
                    </div>
                  </div>
                  <div className="contrib-bar" role="img" aria-label={`${l.delta > 0 ? 'Adds' : l.delta < 0 ? 'Removes' : 'No effect:'} ${Math.abs(l.delta)} points`}>
                    <span className="contrib-zero" />
                    {sign !== 'zero' && <span className="contrib-fill" style={{ width: `${(Math.abs(l.delta) / max) * 50}%`, [l.delta > 0 ? 'left' : 'right']: '50%' }} />}
                  </div>
                  <span className="contrib-delta">{l.delta === 0 ? 'No effect' : `${l.delta > 0 ? '+' : '−'}${Math.abs(l.delta)}`}</span>
                  <span className="contrib-spacer" />
                </li>
              );
            })}
          </ul>
          <footer className="contrib-foot">
            <span>
              {counted.length} finding{counted.length === 1 ? '' : 's'} counted, the latest from each agent
              {aside.length ? ` · ${aside.length} set aside` : ''}
              {context ? ` · policy context ${pointsOf(score.score, context.delta_logit) > 0 ? '+' : '−'}${Math.abs(pointsOf(score.score, context.delta_logit))}` : ''}
            </span>
          </footer>
        </section>

        <div className="report-side">
          <section className="card">
            <header className="card-head">
              <h3>Hard gates</h3>
            </header>
            <ul className="gates is-large">
              <li className={coverageGate || !c.rulesPassed ? 'g-flagged' : 'g-passed'}>
                <span className="gate-dot" />
                <div>
                  Coverage and conditions
                  <span>{coverageGate ? coverageGate.reason : 'Policy active, peril covered, notified in time'}</span>
                </div>
                <b>{coverageGate || !c.rulesPassed ? 'Flagged' : 'Passed'}</b>
              </li>
              <li className={gateTripped ? 'g-flagged' : c.photos.length ? 'g-passed' : 'g-pending'}>
                <span className="gate-dot" />
                <div>
                  Evidence authenticity
                  <span>{gateTripped ? gateTripped.reason : c.photos.length ? 'No photo was found published before the event' : 'The claim has no photos, so nothing was checked'}</span>
                </div>
                <b>{gateTripped ? 'Flagged' : c.photos.length ? 'Passed' : 'Not checked'}</b>
              </li>
            </ul>
            <p className="card-note">A flagged gate sends the case to a person, whatever the score says.</p>
          </section>

          <section className="card">
            <header className="card-head">
              <h3>Flags from the early checks</h3>
              <span className="chip">{c.flags.length}</span>
            </header>
            {c.flags.length ? (
              <ul className="flag-list">
                {c.flags.map((f, i) => (
                  <li key={i} className={`is-${f.severity}`}>
                    <span className="flag-step">{stepName(f.step)}</span>
                    <span className="flag-reason">{f.reason}</span>
                    <span className={`chip${f.severity === 'fail' ? ' v-contradicts' : ''}`}>{f.severity === 'fail' ? 'Fail' : 'Warning'}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="card-note">The early checks raised no flags.</p>
            )}
          </section>

          <details className="card fold">
            <summary>
              <h3>How the verdict was reached</h3>
              <span className="chip">{steps.length} decisions</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <ol className="reason-steps">
              {steps.map((s) => (
                <li key={`${s.who}-${s.at}`}>
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
              <span className={`chip${flaggedPhotos ? ' v-contradicts' : ''}`}>{flaggedPhotos ? `${flaggedPhotos} of ${c.photos.length} flagged` : `${c.photos.length} on file`}</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <PhotoGrid photos={c.photos} t={c.duration} />
          </details>

          {c.map && (
            <details className="card fold">
              <summary>
                <h3>Map</h3>
                <span className="chip">{c.place}</span>
                <ChevronDown size={16} className="fold-chev" />
              </summary>
              <MapCard c={c} t={c.duration} />
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
