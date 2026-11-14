import { ChevronDown, EyeOff, Scale, UserRound, Workflow } from 'lucide-react';
import { useState } from 'react';
import { fmtClock } from '../lib/derive';
import { contributionTitle, stepName } from '../lib/early';
import { agentName, AGENTS, BANDS, isAgent, nr, OUTCOMES } from '../lib/meta';
import { baseOf, fmtScore, pointsOf } from '../lib/score';
import type { CaseFile, Evidence, ScoreStep } from '../lib/types';
import { Aurora, type Tone } from './Aurora';
import { ScoreMeter } from './Cards';
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

  // One row per finding the backend counted (its latest answer from each agent), plus the ones set aside.
  const counted = score.contributions
    .filter((k) => isAgent(k.agent))
    .map((k) => ({ k, e: c.evidence.find((e) => e.agent === k.agent && e.round === k.round && !e.rejected) }))
    .filter((x): x is { k: (typeof score.contributions)[number]; e: Evidence } => !!x.e)
    .map(({ k, e }) => ({ e, off: false, delta: pointsOf(score.score, k.delta_logit) }));
  // Client-data lines carry their own reason; they are counted in the score but are not findings that can be set aside.
  const clientLines = score.contributions
    .filter((k) => k.agent === 'client')
    .map((k) => ({ title: contributionTitle(k), reason: k.reason, delta: pointsOf(score.score, k.delta_logit) }));
  const context = score.contributions.find((k) => k.agent === 'context' && k.delta_logit !== 0);
  const aside = c.evidence.filter((e) => e.rejected).map((e) => ({ e, off: true, delta: 0 }));
  const rows = [...counted.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)), ...aside];
  const max = Math.max(10, ...rows.map((r) => Math.abs(r.delta)), ...clientLines.map((l) => Math.abs(l.delta)));

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
                    <div className="contrib-bar" role="img" aria-label={l.delta === 0 ? 'Fără efect' : `${l.delta > 0 ? 'Adaugă' : 'Scade'} ${Math.abs(l.delta)} puncte`}>
                      <span className="contrib-zero" />
                      {sign !== 'zero' && <span className="contrib-fill" style={{ width: `${(Math.abs(l.delta) / max) * 50}%`, [l.delta > 0 ? 'left' : 'right']: '50%' }} />}
                    </div>
                    <span className="contrib-delta">{l.delta === 0 ? 'Fără efect' : `${l.delta > 0 ? '+' : '−'}${Math.abs(l.delta)}`}</span>
                    <span className="contrib-spacer" />
                  </li>
                );
              })}
            </ul>
            <footer className="contrib-foot">
              <span>
                {nr(counted.length, 'rezultat luat în calcul', 'rezultate luate în calcul')} (cel mai recent de la fiecare agent)
                {clientLines.length ? ` · ${nr(clientLines.length, 'semnal din datele clientului', 'semnale din datele clientului')}` : ''}
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
        </div>

        <div className="report-side">
          <HardGates c={c} score={score} clientLines={clientLines} />
        </div>
      </div>
    </div>
  );
}

/** Points of each client/document score line, matched to its flag by the reason the backend gives both. */
type ClientLine = { title: string; reason?: string | null; delta: number };

/** Steps whose flags cost the score one `client` line each (backend/engine/score.py, CLIENT_FLAG_COST). */
const SCORED_STEPS = new Set(['documents', 'client']);

/**
 * "Condiții obligatorii": what can force a route whatever the score.
 * Policy: the policy rules the backend checked. Authenticity: the clear_fake gate.
 * Then every early flag that reached the Arbitru. Claims stored before the early checks keep the two old gates.
 */
function HardGates({ c, score, clientLines }: { c: CaseFile; score: ScoreStep; clientLines: ClientLine[] }) {
  const fake = score.gates.find((g) => g.kind === 'clear_fake');
  const coverage = score.gates.find((g) => g.kind === 'coverage');
  const early = c.details.documents !== undefined || c.details.client !== undefined || c.details.photos !== undefined;
  const auth = (
    <li className={fake ? 'g-flagged' : c.photos.length ? 'g-passed' : 'g-pending'}>
      <span className="gate-dot" />
      <div>
        Autenticitatea dovezilor
        <span>
          {fake
            ? `${fake.reason} O fotografie publicată înaintea evenimentului impune „${OUTCOMES.antifraud_referral.label}”.`
            : c.photos.length
              ? 'Nicio fotografie nu a fost publicată înaintea evenimentului'
              : 'Nicio fotografie verificată'}
        </span>
      </div>
      <b>{fake ? 'Semnalat' : c.photos.length ? 'În regulă' : 'Neverificat'}</b>
    </li>
  );

  if (!early)
    return (
      <section className="card">
        <header className="card-head">
          <h3>Condiții obligatorii</h3>
        </header>
        <ul className="gates is-large">
          <li className={coverage || !c.rulesPassed ? 'g-flagged' : 'g-passed'}>
            <span className="gate-dot" />
            <div>
              Acoperire și condiții
              <span>{coverage ? coverage.reason : 'Poliță activă, risc acoperit, avizare în termen'}</span>
            </div>
            <b>{coverage || !c.rulesPassed ? 'Semnalat' : 'În regulă'}</b>
          </li>
          {auth}
        </ul>
        <p className="card-note">Dacă o condiție nu este îndeplinită, dosarul ajunge la un inspector, indiferent de scor.</p>
      </section>
    );

  const rules = c.details.policy ?? [];
  const failed = rules.filter((r) => r.status === 'fail');
  const lineFor = (reason: string) => clientLines.find((l) => l.reason === reason);
  return (
    <section className="card">
      <header className="card-head">
        <h3>Condiții obligatorii</h3>
      </header>

      <p className="field-label">Poliță</p>
      <ul className="gates is-large">
        {rules.map((r) => (
          <li key={r.id} className={r.status === 'fail' ? 'g-flagged' : r.status === 'ok' ? 'g-passed' : 'g-pending'}>
            <span className="gate-dot" />
            <div>
              {r.label}
              {(r.note || r.value) && <span>{r.note ?? r.value}</span>}
            </div>
            <b>{r.status === 'fail' ? 'Neîndeplinită' : r.status === 'ok' ? 'În regulă' : r.status === 'flag' ? 'Semnalat' : 'Informativ'}</b>
          </li>
        ))}
        {!rules.length && <li className="g-pending"><span className="gate-dot" /><div>Regulile poliței nu au fost verificate</div><b>Neverificat</b></li>}
      </ul>
      {failed.length > 0 && (
        <p className="card-note">
          Dosarul a fost oprit la verificarea poliței. O regulă neîndeplinită impune „{OUTCOMES.standard_review.label}”, indiferent de scor.
        </p>
      )}

      <p className="field-label">Autenticitate</p>
      <ul className="gates is-large">{auth}</ul>

      <p className="field-label">Semnale transmise Arbitrului</p>
      {c.flags.length ? (
        <ul className="flag-list">
          {c.flags.map((f, i) => {
            const scored = SCORED_STEPS.has(f.step);
            const line = scored ? lineFor(f.reason) : undefined;
            return (
              <li key={i} className={`is-${f.severity}`}>
                <span className="flag-step">{stepName(f.step)}</span>
                <span className="flag-reason">{f.reason}</span>
                <span className={`chip${f.severity === 'fail' ? ' v-contradicts' : ''}`}>
                  {scored ? (line && line.delta ? `Scor ${line.delta > 0 ? '+' : '−'}${Math.abs(line.delta)}` : 'Scade scorul') : f.severity === 'fail' ? 'Neîndeplinit' : 'Atenționare'}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="card-note">Verificările inițiale nu au semnalat nimic.</p>
      )}
      {c.flags.some((f) => SCORED_STEPS.has(f.step)) && (
        <p className="card-note">Fiecare semnal din documente sau din datele clientului scade scorul (−0,25 pe scara logit); liniile apar în „Ce a influențat scorul”.</p>
      )}
    </section>
  );
}
