import { ChevronDown, EyeOff, Scale, Workflow } from 'lucide-react';
import { useState } from 'react';
import { fmtClock } from '../lib/derive';
import { agentName, AGENTS, BANDS, isAgent, nr, OUTCOMES } from '../lib/meta';
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
  const context = score.contributions.find((k) => k.agent === 'context' && k.delta_logit !== 0);
  const aside = c.evidence.filter((e) => e.rejected).map((e) => ({ e, off: true, delta: 0 }));
  const rows = [...counted.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)), ...aside];
  const max = Math.max(10, ...rows.map((r) => Math.abs(r.delta)));

  const flaggedPhotos = c.photos.filter((ph) => ph.status === 'fail').length;
  const planWindow = c.windows.find((w) => w.stage === 'plan');
  const steps = [
    ...(planWindow
      ? [{ at: planWindow.at, icon: Workflow, who: 'Plan', text: `A stabilit ${nr(c.plan.hypotheses.length, 'ipoteză', 'ipoteze')} și a trimis ${c.plan.dispatch.filter((d) => !d.skipped).length} din cei ${AGENTS.length} agenți.` }]
      : []),
    ...c.judge.map((j) => ({ at: j.at, icon: Scale, who: `Arbitru, runda ${j.round}`, text: j.summary })),
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
                Recomandare: <b>{OUTCOMES[score.recommendation].action.toLowerCase()}</b>
              </p>
            </div>
          </div>
          {c.rationale && <p className="verdict-why">{c.rationale}</p>}
          <ScoreMeter score={score.score} band={score.band} />
        </div>
        <div className="verdict-side">{children}</div>
      </section>

      <div className="report-grid">
        <div className="report-side">
          <details className="card contrib fold">
            <summary>
              <h3>Ce a influențat scorul</h3>
              <span className="chip" title="Scorul înainte de rezultatele agenților">Scor inițial: {baseOf(score)}</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <p className="card-sub contrib-intro">Câte puncte a adăugat sau a scăzut fiecare rezultat. Dacă excludeți un rezultat, scorul se recalculează fără el; operația nu se poate anula.</p>
            <div className="contrib-axis" aria-hidden="true">
              <span />
              <span className="axis-labels">
                <i>Împotriva daunei</i>
                <i>Pentru daună</i>
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
                          {e.round > 1 ? `, runda ${e.round}` : ''} · {e.source}
                        </p>
                        {e.detail && <p className="contrib-src">{e.detail}</p>}
                      </div>
                    </div>
                    <div className="contrib-bar" role="img" aria-label={delta === 0 ? 'Fără efect' : `${delta > 0 ? 'Adaugă' : 'Scade'} ${Math.abs(delta)} puncte`}>
                      <span className="contrib-zero" />
                      {sign !== 'zero' && <span className="contrib-fill" style={{ width: `${w}%`, [delta > 0 ? 'left' : 'right']: '50%' }} />}
                    </div>
                    <span className="contrib-delta">{off ? 'Exclus' : delta === 0 ? 'Fără efect' : `${delta > 0 ? '+' : '−'}${Math.abs(delta)}`}</span>
                    {off || c.decision ? (
                      <span className="contrib-spacer" />
                    ) : arming === e.id ? (
                      <button type="button" className="btn btn-quiet contrib-confirm" disabled={busy} onClick={() => { setArming(null); onReject(e.id); }} onBlur={() => setArming(null)}>
                        Confirmați
                      </button>
                    ) : (
                      <button type="button" className="icon-btn" onClick={() => setArming(e.id)} aria-label={`Excludeți rezultatul: ${e.title}`} title="Excludeți acest rezultat (definitiv)">
                        <EyeOff size={14} />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            <footer className="contrib-foot">
              <span>
                {nr(counted.length, 'rezultat luat în calcul', 'rezultate luate în calcul')} (cel mai recent de la fiecare agent)
                {aside.length ? ` · ${aside.length} excluse` : ''}
                {context ? ` · contextul poliței ${pointsOf(score.score, context.delta_logit) > 0 ? '+' : '−'}${Math.abs(pointsOf(score.score, context.delta_logit))}` : ''}
              </span>
            </footer>
          </details>

          <details className="card fold">
            <summary>
              <h3>Cum s-a ajuns la verdict</h3>
              <span className="chip">{nr(steps.length, 'decizie', 'decizii')}</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <ol className="reason-steps">
              {steps.map((s) => (
                <li key={`${s.who}-${s.at}`}>
                  <button type="button" onClick={() => onJump(s.at)} title="Vedeți acest pas">
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
              <h3>Fotografiile depuse</h3>
              <span className={`chip${flaggedPhotos ? ' v-contradicts' : ''}`}>{flaggedPhotos ? `${flaggedPhotos} din ${c.photos.length} semnalate` : `${c.photos.length} la dosar`}</span>
              <ChevronDown size={16} className="fold-chev" />
            </summary>
            <PhotoGrid photos={c.photos} t={c.duration} />
          </details>

          {c.map && (
            <details className="card fold">
              <summary>
                <h3>Hartă</h3>
                <span className="chip">{c.place}</span>
                <ChevronDown size={16} className="fold-chev" />
              </summary>
              <MapCard c={c} t={c.duration} />
            </details>
          )}
        </div>

        <div className="report-side">
          <section className="card">
            <header className="card-head">
              <h3>Condiții obligatorii</h3>
            </header>
            <ul className="gates is-large">
              <li className={coverageGate || !c.rulesPassed ? 'g-flagged' : 'g-passed'}>
                <span className="gate-dot" />
                <div>
                  Acoperire și condiții
                  <span>{coverageGate ? coverageGate.reason : 'Poliță activă, risc acoperit, avizare în termen'}</span>
                </div>
                <b>{coverageGate || !c.rulesPassed ? 'Semnalat' : 'În regulă'}</b>
              </li>
              <li className={gateTripped ? 'g-flagged' : c.photos.length ? 'g-passed' : 'g-pending'}>
                <span className="gate-dot" />
                <div>
                  Autenticitatea dovezilor
                  <span>{gateTripped ? gateTripped.reason : c.photos.length ? 'Nicio fotografie nu a fost publicată înaintea evenimentului' : 'Dosarul nu are fotografii de verificat'}</span>
                </div>
                <b>{gateTripped ? 'Semnalat' : c.photos.length ? 'În regulă' : 'Neverificat'}</b>
              </li>
            </ul>
            <p className="card-note">Dacă o condiție nu este îndeplinită, dosarul ajunge la un inspector, indiferent de scor.</p>
          </section>
        </div>
      </div>
    </div>
  );
}
