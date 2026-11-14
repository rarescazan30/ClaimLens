import { ArrowLeft, ArrowRight, Camera, Check, FileText, Gauge, ListChecks, Map as MapIcon, Play, Radio, Scale, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { API_URL } from '../api/client';
import { useCase, type CaseActions } from '../api/hooks';
import { activeStage, currentRound, fmtClock, laneStates, loopState, scoreAt, stageStatuses } from '../lib/derive';
import { useRun } from '../lib/hooks';
import { agentName, BANDS, isAgent, ORDER, OUTCOMES, STAGES } from '../lib/meta';
import { fmtScore, pointsOf } from '../lib/score';
import type { AgentId, CaseFile, DetailItem, StageId } from '../lib/types';
import type { Tone } from './Aurora';
import { ClaimCard, MapCard, ScoreCard, ScoreNumber, type GateState } from './Cards';
import { DecisionPanel } from './DecisionPanel';
import { EvidenceDrawer } from './EvidenceDrawer';
import { Pipeline } from './Pipeline';
import { ReplayBar } from './ReplayBar';
import { Report } from './Report';
import { StageDetail } from './StageDetail';
import { Empty, Kicker, PhotoGrid } from './ui';

function ScoreRing({ score }: { score: number }) {
  const r = 44;
  const len = 2 * Math.PI * r;
  return (
    <div className="score-ring" role="img" aria-label={`Score ${fmtScore(score)} out of 100`}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle className="ring-bg" cx="50" cy="50" r={r} />
        <circle className="ring-fg" cx="50" cy="50" r={r} strokeDasharray={`${(score / 100) * len} ${len}`} />
      </svg>
      <span className="ring-num">
        <strong>{fmtScore(score)}</strong>
        <small>out of 100</small>
      </span>
    </div>
  );
}

// Resting headlines carry the accent on their second half; live ones stay plain so they read at a glance.
const HEADLINE_SPLIT: Record<string, [string, string]> = {
  'Ready to investigate': ['Ready to', 'investigate.'],
  'Ready to replay': ['Ready to', 'replay.'],
  'Waiting for your decision': ['Waiting for', 'your decision.'],
  'Decision logged': ['Decision', 'logged.'],
};

const DOCK_GROUPS = [
  { id: 'claim', label: 'The claim' },
  { id: 'run', label: 'Investigation' },
  { id: 'result', label: 'Result' },
] as const;

interface LedgerLine {
  id: string;
  title: string;
  delta: number;
}

/** The score as it builds: the backend's latest number, and what each agent's finding is worth in it. */
function LiveScore({ score, band, phase, lines, onOpen }: { score?: number; band: string; phase: string; lines: LedgerLine[]; onOpen: () => void }) {
  const waiting = score === undefined;
  return (
    <button type="button" className={`card live-score b-${band}${waiting ? ' is-waiting' : ''}`} onClick={onOpen} aria-label={waiting ? 'Plausibility score: waiting for evidence. Open score details' : `Plausibility score ${fmtScore(score)}. Open score details`}>
      <span className="live-score-top">
        <span>Plausibility so far</span>
        <span className={`chip pill${waiting ? '' : ' is-live'}`}>{phase === 'idle' ? 'Not started' : waiting ? 'Waiting' : 'Building'}</span>
      </span>
      <span className="live-score-num">{waiting ? '–' : <ScoreNumber score={score} ms={700} />}</span>
      <span className="live-score-sub">{waiting ? 'Appears after the first round of agents' : `${BANDS[band as keyof typeof BANDS].label} · out of 100`}</span>
      {lines.length > 0 && (
        <span className="ledger">
          {lines.slice(0, 4).map((l) => (
            <span key={l.id} className={`ledger-row ${l.delta > 0 ? 'is-plus' : l.delta < 0 ? 'is-minus' : 'is-zero'}`}>
              <span>{l.title}</span>
              <b>{l.delta === 0 ? '0' : `${l.delta > 0 ? '+' : '−'}${Math.abs(l.delta)}`}</b>
            </span>
          ))}
        </span>
      )}
    </button>
  );
}

export function CaseView({ id, initialT, initialTab }: { id: string; initialT?: number; initialTab?: string }) {
  const { c, live, error, actions } = useCase(id);

  if (error && !c)
    return (
      <div className="page">
        <a className="back" href="#/"><ArrowLeft size={15} /> Claims queue</a>
        <div className="card"><Empty title="The backend is not answering" body={`${error} The address is set by VITE_API_URL, now ${API_URL}.`} /></div>
      </div>
    );
  if (c === undefined) return <div className="page"><div className="card loading-card"><span className="spinner" /> Loading case</div></div>;
  if (c === null)
    return (
      <div className="page">
        <a className="back" href="#/"><ArrowLeft size={15} /> Claims queue</a>
        <div className="card"><Empty title={`No claim ${id}`} body="The backend has no claim with this number." /></div>
      </div>
    );
  return <CaseInner key={c.id} c={c} live={live} actions={actions} initialT={initialT} initialTab={initialTab} />;
}

type Panel = 'step' | 'score' | 'map' | 'claim' | 'photos' | 'verdict';

function CaseInner({ c, live, actions, initialT, initialTab }: { c: CaseFile; live: boolean; actions: CaseActions; initialT?: number; initialTab?: string }) {
  const finished = c.status === 'awaiting_decision' || c.status === 'decided';
  // A finished claim opens on its result; the replay bar goes back through the run.
  const run = useRun(c.duration, initialT ?? (finished ? c.duration : 0), live, c.edge);
  const [panel, setPanel] = useState<Panel | null>(initialTab === 'report' ? 'verdict' : null);
  const [pinned, setPinned] = useState<StageId | null>(null);
  const [agentFocus, setAgentFocus] = useState<AgentId | null>(null);
  const [drawer, setDrawer] = useState<AgentId | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  /** Runs one backend action; a failure is shown on the page instead of being lost. */
  const act = (fn: () => Promise<void>) => {
    setActionError('');
    setBusy(true);
    fn()
      .catch((e: Error) => setActionError(e.message))
      .finally(() => setBusy(false));
  };

  // When a live run ends: a run served from saved responses was over in a blink, so play it back
  // (from the adjuster's question, if this run answered one). A run that took real time was already watched.
  const wasLive = useRef(live);
  useEffect(() => {
    if (wasLive.current && !live) {
      const from = c.questions.length ? c.questions[c.questions.length - 1].at : 0;
      if (c.paced) {
        run.seek(from);
        run.play();
      } else run.finish();
      setPinned(null);
    }
    wasLive.current = live;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live]);

  // Space toggles the replay unless the user is typing.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (live || e.code !== 'Space' || el.closest('input, textarea, button, [role="button"], a')) return;
      e.preventDefault();
      run.toggle();
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [run.toggle, live]);

  const never = c.status === 'received' && !live; // never investigated
  const started = !never && (live || run.time > 0 || run.playing);
  const t = started ? run.time : -1;
  const done = !live && finished && t >= c.duration;

  const status = stageStatuses(c, t, !!c.decision);
  const lanes = laneStates(c, t);
  const active = activeStage(status);
  const round = currentRound(c, t);
  const loop = loopState(c, t);
  const shown: StageId = pinned ?? active ?? (done ? 'review' : 'intake');

  // The score is whatever the backend last computed at this point of the run. Nothing is recomputed here.
  const now = scoreAt(c, t);
  const band = now?.band ?? 'uncertain';
  const evidence = c.evidence.filter((e) => e.at <= t);
  const gateTripped = !!now?.gates.some((g) => g.kind === 'clear_fake');
  const coverageBlocked = !!now?.gates.some((g) => g.kind === 'coverage');
  const phase = !started ? 'idle' : !now ? 'base' : done ? 'final' : 'provisional';

  const policyWindow = c.windows.find((w) => w.stage === 'policy');
  const coverage: GateState = !policyWindow || t < policyWindow.at + policyWindow.dur ? 'pending' : c.rulesPassed && !coverageBlocked ? 'passed' : 'flagged';
  const forensics = c.evidence.find((e) => e.agent === 'photo_forensics' && e.at <= t);
  const authenticity: GateState = gateTripped ? 'flagged' : !c.photos.length ? 'none' : forensics ? 'passed' : 'pending';

  const lastWindow = c.windows[c.windows.length - 1];
  const tone: Tone = !done && t < lastWindow.at ? 'accent' : band === 'unlikely' ? 'bad' : band === 'uncertain' ? 'warn' : 'good';

  const verdictWindow = [...c.windows].reverse().find((w) => w.stage === 'verdict');
  const sourceCount = new Set(evidence.map((e) => e.source)).size;
  const verdictItems: DetailItem[] = verdictWindow && now
    ? [
        { label: 'Plausibility score', value: `${fmtScore(now.score)} · ${BANDS[now.band].label}`, status: now.band === 'unlikely' ? 'fail' : now.band === 'uncertain' ? 'flag' : 'ok' },
        { label: 'Coverage gate', value: coverage === 'flagged' ? 'Flagged' : 'Passed', status: coverage === 'flagged' ? 'fail' : 'ok' },
        { label: 'Authenticity gate', value: gateTripped ? 'Flagged' : c.photos.length ? 'Passed' : 'No photos to check', status: gateTripped ? 'fail' : c.photos.length ? 'ok' : 'info' },
        { label: 'Recommended route', value: OUTCOMES[now.recommendation].label, status: 'info' },
        { label: 'Case file assembled', value: `${evidence.length} findings · ${sourceCount} sources`, status: 'ok' },
      ].map((x, i, all) => ({ ...x, id: `v${i}`, at: verdictWindow.at + ((i + 1) * verdictWindow.dur) / (all.length + 1) }) as DetailItem)
    : [];

  // What each agent's latest finding is worth in the current score, biggest first.
  const ledger: LedgerLine[] = (now?.contributions ?? [])
    .filter((k) => isAgent(k.agent) || k.delta_logit !== 0)
    .map((k) => ({ id: `${k.agent}.${k.round}`, title: agentName(k.agent), delta: pointsOf(now!.score, k.delta_logit) }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  const liveMeta = active ? STAGES.find((s) => s.id === active)! : null;
  const askedThisRound = c.questions.some((q) => q.round === round);
  const headline = never
    ? 'Ready to investigate'
    : !started
      ? 'Ready to replay'
      : c.decision && done
        ? 'Decision logged'
        : liveMeta
          ? active === 'agents' && round > 1
            ? `Re-checking with ${c.runs.filter((r) => r.round === round).length || 'the'} agent${c.runs.filter((r) => r.round === round).length === 1 ? '' : 's'}`
            : liveMeta.live
          : 'Waiting for your decision';
  const stepNo = active ? STAGES.findIndex((s) => s.id === active) + 1 : done ? STAGES.length : 0;

  const select = (stage: StageId, agent?: AgentId) => {
    if (agent) {
      setDrawer(agent);
      return;
    }
    setAgentFocus(null);
    setPinned(stage);
    setPanel('step');
  };
  const toggle = (p: Panel) => setPanel((cur) => (cur === p ? null : p));

  // One line of "what just happened", so the closed view still feels alive.
  const feed = [
    ...ORDER.flatMap((sid) => (c.details[sid] ?? []).map((i) => ({ at: i.at, text: `${i.label}${i.value ? `: ${i.value}` : ''}` }))),
    ...c.runs.map((r) => ({ at: r.at + r.dur, text: `${agentName(r.agent)}: ${r.finding}` })),
    ...c.judge.map((j) => ({ at: j.at + j.dur, text: `Judge: ${j.summary}` })),
  ]
    .filter((x) => x.at <= t)
    .sort((x, y) => x.at - y.at);
  const latest = feed[feed.length - 1];
  const flaggedPhotos = c.photos.filter((ph) => ph.at <= t && ph.status === 'fail').length;

  const approve = () => act(() => actions.decide({ decision: 'approve' }));

  const decisionPanel = (
    <DecisionPanel
      ready={done}
      recommended={now?.recommendation}
      decision={c.decision}
      questions={c.questions}
      busy={busy}
      onApprove={approve}
      onOverride={(outcome, reason) => act(() => actions.decide({ decision: 'modify', outcome, reason }))}
      onAsk={(q) => act(() => actions.ask(q))}
    />
  );

  // Read top to bottom in the order an adjuster works: what was claimed, what the run is doing, what it concluded.
  const dock: { id: Panel; icon: typeof Gauge; label: string; meta?: string; alert?: boolean; group: 'claim' | 'run' | 'result' }[] = [
    { id: 'claim', icon: FileText, label: 'Claim', group: 'claim' },
    { id: 'photos', icon: Camera, label: 'Photos', meta: flaggedPhotos ? `${flaggedPhotos} flagged` : String(c.photos.length), alert: flaggedPhotos > 0, group: 'claim' },
    ...(c.map ? [{ id: 'map' as const, icon: MapIcon, label: 'Map', group: 'claim' as const }] : []),
    { id: 'step', icon: ListChecks, label: 'Step details', meta: STAGES.find((x) => x.id === shown)!.short, group: 'run' },
    { id: 'score', icon: Gauge, label: 'Score', meta: now ? fmtScore(now.score) : undefined, group: 'run' },
    { id: 'verdict', icon: Scale, label: 'Full report', group: 'result' },
  ];

  return (
    <div className="page case">
      <div className="run-progress" aria-hidden="true">
        <span style={{ transform: `scaleX(${started && !live ? Math.min(1, run.time / c.duration) : 0})` }} />
      </div>
      <a className="back" href="#/">
        <ArrowLeft size={15} /> Claims queue
      </a>
      <div className="case-context">
        <span className="case-eyebrow">
          {c.typeLabel} claim · {c.place}
        </span>
        <span className="case-facts">
          {c.claimed} · {c.lag}
        </span>
        <span className={`live-chip${live || (run.playing && !done) ? ' is-on' : ''}`}>
          <span className="live-dot is-on" />
          {live ? 'Live investigation' : never ? 'Not investigated yet' : done ? 'Investigation complete' : run.playing ? 'Replaying the investigation' : 'Replay paused'}
        </span>
      </div>

      <div className="case-layout">
      <nav className="side-nav" aria-label="Case panels">
        {DOCK_GROUPS.map((g) => (
          <div className="side-group" key={g.id}>
            <p className="side-label">{g.label}</p>
            {dock
              .filter((d) => d.group === g.id)
              .map((d) => (
                <button type="button" key={d.id} className={`side-btn${panel === d.id ? ' is-on' : ''}${d.alert ? ' is-alert' : ''}${d.group === 'result' && done ? ' is-ready' : ''}`} aria-expanded={panel === d.id} onClick={() => toggle(d.id)}>
                  <d.icon size={16} />
                  <span className="side-name">{d.label}</span>
                  {d.meta && <span className="side-meta">{d.meta}</span>}
                </button>
              ))}
          </div>
        ))}
      </nav>
      <div className="case-main">
      {actionError && (
        <p className="form-error action-error" role="alert">
          The backend refused that: {actionError}
        </p>
      )}
      {c.error && (
        <p className="form-error action-error" role="alert">
          {c.error}
        </p>
      )}
      <div className={`stage-top${done ? ' is-done' : ''}`}>
      <section className="stage-head" aria-live="polite">
        {started && (
          <Kicker n={String(stepNo || 1).padStart(2, '0')}>
            {`${liveMeta ? liveMeta.short : 'Review'} · ${fmtClock(run.time)}${round > 1 ? ` · round ${round}` : ''}`}
          </Kicker>
        )}
        <h1 className={`stage-title${(live || run.playing) && !done ? ' is-working' : ''}`} key={headline}>
          {HEADLINE_SPLIT[headline] ? (
            <>
              {HEADLINE_SPLIT[headline][0]} <span className="hl">{HEADLINE_SPLIT[headline][1]}</span>
            </>
          ) : (
            headline
          )}
        </h1>
        {started && (
        <p className="stage-sub">
          {done
              ? c.decision
                ? 'Your decision is recorded. The full report keeps every source.'
                : 'The Judge has stopped. Approve the recommendation, or open the full report to see why.'
              : liveMeta
                ? active === 'agents' && round > 1
                  ? askedThisRound
                    ? 'An agent is answering your question.'
                    : 'The Judge found points it could not settle and sent specific agents back with narrower questions.'
                  : liveMeta.help
                : 'The recommendation is ready for you.'}
        </p>
        )}
        <div className="stage-cta">
          {never ? (
            <button type="button" className="btn btn-primary is-large" disabled={busy} onClick={() => act(actions.start)}>
              <Play size={15} fill="currentColor" />
              Start investigation
            </button>
          ) : !started ? (
            <button type="button" className="btn btn-primary is-large" onClick={run.play}>
              <Play size={15} fill="currentColor" />
              Replay investigation
            </button>
          ) : pinned && !done ? (
            <button type="button" className="btn btn-secondary" onClick={() => { setPinned(null); setAgentFocus(null); }}>
              <Radio size={14} />
              Follow live step
            </button>
          ) : null}
        </div>
      </section>
      {!done && <LiveScore score={now?.score} band={band} phase={phase} lines={ledger} onOpen={() => toggle('score')} />}
      </div>

      <section className={`card rail-card tone-${tone}`}>
        <Pipeline status={status} lanes={lanes} loop={loop} round={round} active={active} selected={shown} tone={tone} started={started} onSelect={select} />
      </section>
      {!never && <ReplayBar c={c} run={run} live={live} busy={busy} onRerun={() => act(actions.start)} />}

      {done && now && (
        <section className={`card verdict-strip b-${now.band}`}>
          <ScoreRing score={now.score} />
          <div className="verdict-strip-text">
            <h2>{BANDS[now.band].label}</h2>
            <p className="verdict-route">Recommended: {OUTCOMES[now.recommendation].action.toLowerCase()}</p>
            {c.rationale && <p>{c.rationale}</p>}
          </div>
          <div className="verdict-strip-actions">
            {c.decision ? (
              <span className="chip st-done">
                <Check size={12} strokeWidth={3} />
                {OUTCOMES[c.decision.outcome].label} · logged {c.decision.at}
              </span>
            ) : (
              <button type="button" className="btn btn-primary is-large" disabled={busy} onClick={approve}>
                <Check size={15} strokeWidth={2.6} />
                Approve
              </button>
            )}
            <button type="button" className="btn btn-secondary is-large" onClick={() => setPanel('verdict')}>
              See why
              <ArrowRight size={15} />
            </button>
          </div>
        </section>
      )}

      {!panel && !done && started && (
        <p className="ticker" key={latest?.text ?? 'hint'} aria-live="polite">
          {latest ? latest.text : 'Starting…'}
        </p>
      )}

      {panel && (
        <div className={`panel${panel === 'step' || panel === 'verdict' ? '' : ' is-narrow'}`} key={panel}>
          <button type="button" className="icon-btn panel-close" aria-label="Close panel" onClick={() => setPanel(null)}>
            <X size={16} />
          </button>
          {panel === 'step' && (
            <StageDetail c={c} t={t} stage={shown} status={status[shown]} agentFocus={agentFocus} verdictItems={verdictItems}>
              {shown === 'review' ? decisionPanel : null}
            </StageDetail>
          )}
          {panel === 'score' && <ScoreCard score={now?.score} band={now?.band} evidenceCount={now?.contributions.filter((k) => isAgent(k.agent)).length ?? 0} phase={phase} coverage={coverage} authenticity={authenticity} />}
          {panel === 'map' && c.map && <MapCard c={c} t={t} />}
          {panel === 'claim' && <ClaimCard c={c} />}
          {panel === 'photos' && (
            <section className="card">
              <header className="card-head">
                <h3>Claimant photos</h3>
                <span className="chip">{c.photos.length} file{c.photos.length === 1 ? '' : 's'}</span>
              </header>
              <PhotoGrid photos={c.photos} t={t} />
            </section>
          )}
          {panel === 'verdict' &&
            (done && now ? (
              <Report
                c={c}
                score={now}
                tone={tone}
                busy={busy}
                onReject={(eid) => act(() => actions.reject(eid))}
                onJump={(at) => {
                  run.pause();
                  run.seek(at + 1);
                  setPinned(null);
                  setPanel('step');
                }}
              >
                {decisionPanel}
              </Report>
            ) : (
              <div className="card">
                <Empty
                  title="The report is assembled when the Judge stops"
                  body={never ? 'Start the investigation to build it.' : live ? `The run is at step ${stepNo || 1} of ${STAGES.length}.` : 'The replay has not reached the verdict yet.'}
                />
                {!never && !live && (
                  <div className="empty-actions">
                    <button type="button" className="btn btn-secondary" onClick={run.finish}>
                      Skip to verdict
                    </button>
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
      </div>
      </div>
      {drawer && (
        <EvidenceDrawer
          c={c}
          agent={drawer}
          t={t}
          onClose={() => setDrawer(null)}
          onOpenSteps={() => {
            setAgentFocus(drawer);
            setPinned('agents');
            setPanel('step');
            setDrawer(null);
          }}
        />
      )}
    </div>
  );
}
