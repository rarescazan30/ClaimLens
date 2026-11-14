import { ArrowLeft, ArrowRight, Camera, Check, FileText, Gauge, ListChecks, Map as MapIcon, Play, Radio, Scale, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { activeStage, currentRound, fmtClock, laneStates, loopState, stageStatuses } from '../lib/derive';
import { getSession, saveSession, useEased, useRun, type Decision } from '../lib/hooks';
import { bandOf, computeScore, routeFor } from '../lib/score';
import { getCase } from '../mock/api';
import { agentName, BANDS, ORDER, ROUTES, STAGES } from '../mock/meta';
import type { AgentId, CaseFile, DetailItem, StageId } from '../mock/types';
import type { Tone } from './Aurora';
import { ClaimCard, MapCard, ScoreCard } from './Cards';
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
    <div className="score-ring" role="img" aria-label={`Score ${score} out of 100`}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle className="ring-bg" cx="50" cy="50" r={r} />
        <circle className="ring-fg" cx="50" cy="50" r={r} strokeDasharray={`${(score / 100) * len} ${len}`} />
      </svg>
      <span className="ring-num">
        <strong>{score}</strong>
        <small>out of 100</small>
      </span>
    </div>
  );
}

// Resting headlines carry the accent on their second half; live ones stay plain so they read at a glance.
const HEADLINE_SPLIT: Record<string, [string, string]> = {
  'Ready to investigate': ['Ready to', 'investigate.'],
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

/** The score as it builds: one big figure, and the findings that moved it, newest first. */
function LiveScore({ score, band, phase, lines, onOpen }: { score: number; band: string; phase: string; lines: LedgerLine[]; onOpen: () => void }) {
  const eased = useEased(score, 700);
  const waiting = phase === 'idle' || phase === 'base';
  return (
    <button type="button" className={`card live-score b-${band}${waiting ? ' is-waiting' : ''}`} onClick={onOpen} aria-label={waiting ? 'Plausibility score: waiting for evidence. Open score details' : `Plausibility score ${score}. Open score details`}>
      <span className="live-score-top">
        <span>Plausibility so far</span>
        <span className={`chip pill${waiting ? '' : ' is-live'}`}>{phase === 'idle' ? 'Not started' : phase === 'base' ? 'Waiting' : 'Building'}</span>
      </span>
      <span className="live-score-num">{waiting ? '–' : Math.round(eased)}</span>
      <span className="live-score-sub">{waiting ? 'Starts once the agents report back' : `${BANDS[band as keyof typeof BANDS].label} · out of 100`}</span>
      {lines.length > 0 && (
        <span className="ledger">
          {lines.slice(-4).map((l) => (
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
  const [c, setC] = useState<CaseFile | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    setC(undefined);
    getCase(id).then((x) => live && setC(x ?? null));
    return () => {
      live = false;
    };
  }, [id]);

  if (c === undefined) return <div className="page"><div className="card loading-card"><span className="spinner" /> Loading case</div></div>;
  if (c === null)
    return (
      <div className="page">
        <a className="back" href="#/"><ArrowLeft size={15} /> Claims queue</a>
        <div className="card"><Empty title={`No full trace for ${id}`} body="The mock data carries complete runs for C-1042 and C-1047." /></div>
      </div>
    );
  return <CaseInner key={c.id} c={c} initialT={initialT} initialTab={initialTab} />;
}

type Panel = 'step' | 'score' | 'map' | 'claim' | 'photos' | 'verdict';

function CaseInner({ c, initialT, initialTab }: { c: CaseFile; initialT?: number; initialTab?: string }) {
  const saved = useMemo(() => getSession(c.id), [c.id]);
  const run = useRun(c.duration, initialT ?? saved.time);
  const [decision, setDecision] = useState<Decision | undefined>(saved.decision);
  const [dismissed, setDismissed] = useState<string[]>(saved.dismissed);
  const [requests, setRequests] = useState<string[]>(saved.requests);
  const [edits, setEdits] = useState<Record<string, string>>(saved.edits);
  const [panel, setPanel] = useState<Panel | null>(initialTab === 'report' ? 'verdict' : null);
  const [pinned, setPinned] = useState<StageId | null>(null);
  const [agentFocus, setAgentFocus] = useState<AgentId | null>(null);
  const [drawer, setDrawer] = useState<AgentId | null>(null);

  const [completed, setCompleted] = useState(!!saved.completed || (initialT ?? saved.time) >= c.duration);
  useEffect(() => {
    if (run.time >= c.duration) setCompleted(true);
  }, [run.time, c.duration]);
  useEffect(() => {
    saveSession(c.id, { time: run.time, completed, decision, dismissed, requests, edits });
  }, [c.id, run.time, completed, decision, dismissed, requests, edits]);

  // Space toggles the replay unless the user is typing.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.code !== 'Space' || el.closest('input, textarea, button, [role="button"], a')) return;
      e.preventDefault();
      run.toggle();
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [run.toggle]);

  const started = run.time > 0 || run.playing;
  const t = started ? run.time : -1;
  const done = t >= c.duration;

  const status = stageStatuses(c, t, !!decision);
  const lanes = laneStates(c, t);
  const active = activeStage(status);
  const round = currentRound(c, t);
  const loop = loopState(c, t);
  const shown: StageId = pinned ?? active ?? (done ? 'review' : 'intake');

  const evidence = c.evidence.filter((e) => e.at <= t);
  const live = evidence.filter((e) => !dismissed.includes(e.id));
  const score = computeScore(c.p0, live);
  const band = bandOf(score);
  const gateTripped = !!c.gate && t >= c.gate.at && !dismissed.includes(c.gate.evidence);
  const route = routeFor(score, gateTripped);

  const policyEnd = c.windows.find((w) => w.stage === 'policy')!;
  const coverage = t >= policyEnd.at + policyEnd.dur ? 'passed' : 'pending';
  const photosEnd = c.windows.find((w) => w.stage === 'photos')!;
  const authenticity = gateTripped ? 'flagged' : done || (!c.gate && t >= photosEnd.at + photosEnd.dur) ? 'passed' : 'pending';
  const phase = !started ? 'idle' : done ? 'final' : evidence.length ? 'provisional' : 'base';

  const tone: Tone = !done && t < c.windows[c.windows.length - 1].at ? 'accent' : band === 'unlikely' ? 'bad' : band === 'uncertain' ? 'warn' : 'good';

  const verdictWindow = c.windows.find((w) => w.stage === 'verdict')!;
  const sourceCount = new Set(evidence.map((e) => e.source)).size;
  const verdictItems: DetailItem[] = [
    { id: 'v1', kind: 'check', label: 'Plausibility score', value: `${score} · ${BANDS[band].label}`, status: band === 'unlikely' ? 'fail' : band === 'uncertain' ? 'flag' : 'ok' },
    { id: 'v2', kind: 'check', label: 'Coverage gate', value: 'Passed', status: 'ok' },
    { id: 'v3', kind: 'check', label: 'Authenticity gate', value: gateTripped ? 'Flagged' : 'Passed', status: gateTripped ? 'fail' : 'ok' },
    { id: 'v4', kind: 'check', label: 'Recommended route', value: ROUTES[route].label, status: 'info' },
    { id: 'v5', kind: 'check', label: 'Case file assembled', value: `${evidence.length} findings · ${sourceCount} sources`, status: 'ok' },
  ].map((x, i) => ({ ...x, at: verdictWindow.at + 250 + i * 300 }) as DetailItem);

  // Each finding's move on the score at the moment it arrived.
  const ledger: LedgerLine[] = live.map((e, i) => ({
    id: e.id,
    title: e.title,
    delta: computeScore(c.p0, live.slice(0, i + 1)) - computeScore(c.p0, live.slice(0, i)),
  }));

  const liveMeta = active ? STAGES.find((s) => s.id === active)! : null;
  const headline = !started
    ? 'Ready to investigate'
    : decision && done
      ? 'Decision logged'
      : liveMeta
        ? active === 'agents' && round > 1
          ? `Re-checking with ${c.runs.filter((r) => r.round === round).length} agents`
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
    ...c.judge.map((j) => ({ at: j.at + j.dur * 0.75, text: `Judge: ${j.summary}` })),
  ]
    .filter((x) => x.at <= t)
    .sort((x, y) => x.at - y.at);
  const latest = feed[feed.length - 1];
  const flaggedPhotos = c.photos.filter((ph) => [...ph.states].reverse().find((st) => st.at <= t)?.status === 'fail').length;

  const approve = () => setDecision({ route, kind: 'approved', at: new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) });

  const decisionPanel = (
    <DecisionPanel ready={done} recommended={route} decision={decision} requests={requests} onDecide={setDecision} onAsk={(q) => setRequests((r) => [...r, q])} />
  );

  // Read top to bottom in the order an adjuster works: what was claimed, what the run is doing, what it concluded.
  const dock: { id: Panel; icon: typeof Gauge; label: string; meta?: string; alert?: boolean; group: 'claim' | 'run' | 'result' }[] = [
    { id: 'claim', icon: FileText, label: 'Claim', group: 'claim' },
    { id: 'photos', icon: Camera, label: 'Photos', meta: flaggedPhotos ? `${flaggedPhotos} flagged` : String(c.photos.length), alert: flaggedPhotos > 0, group: 'claim' },
    { id: 'map', icon: MapIcon, label: 'Map', group: 'claim' },
    { id: 'step', icon: ListChecks, label: 'Step details', meta: STAGES.find((x) => x.id === shown)!.short, group: 'run' },
    { id: 'score', icon: Gauge, label: 'Score', meta: started ? String(score) : undefined, group: 'run' },
    { id: 'verdict', icon: Scale, label: 'Full report', group: 'result' },
  ];

  return (
    <div className="page case">
      <div className="run-progress" aria-hidden="true">
        <span style={{ transform: `scaleX(${started ? Math.min(1, run.time / c.duration) : 0})` }} />
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
        <span className={`live-chip${run.playing && !done ? ' is-on' : ''}`}>
          <span className="live-dot is-on" />
          {run.playing && !done ? 'Live investigation' : done ? 'Investigation complete' : started ? 'Paused' : 'Not started'}
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
      <div className={`stage-top${done ? ' is-done' : ''}`}>
      <section className="stage-head" aria-live="polite">
        {started && (
          <Kicker n={String(stepNo || 1).padStart(2, '0')}>
            {`${liveMeta ? liveMeta.short : 'Review'} · ${fmtClock(run.time)}${round > 1 ? ' · round 2' : ''}`}
          </Kicker>
        )}
        <h1 className={`stage-title${run.playing && !done ? ' is-working' : ''}`} key={headline}>
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
              ? 'The Judge has stopped. Approve the recommendation, or open the full report to see why.'
              : liveMeta
                ? active === 'agents' && round > 1
                  ? 'The Judge found two points it could not settle and sent specific agents back with narrower questions.'
                  : liveMeta.help
                : 'The recommendation is ready for you.'}
        </p>
        )}
        <div className="stage-cta">
          {!started ? (
            <button type="button" className="btn btn-primary is-large" onClick={run.play}>
              <Play size={15} fill="currentColor" />
              Start investigation
            </button>
          ) : pinned && !done ? (
            <button type="button" className="btn btn-secondary" onClick={() => { setPinned(null); setAgentFocus(null); }}>
              <Radio size={14} />
              Follow live step
            </button>
          ) : null}
        </div>
      </section>
      {!done && <LiveScore score={score} band={band} phase={phase} lines={ledger} onOpen={() => toggle('score')} />}
      </div>

      <section className={`card rail-card tone-${tone}`}>
        <Pipeline status={status} lanes={lanes} loop={loop} active={active} selected={shown} tone={tone} started={started} onSelect={select} />
      </section>
      <ReplayBar c={c} run={run} />

      {done && (
        <section className={`card verdict-strip b-${band}`}>
          <ScoreRing score={score} />
          <div className="verdict-strip-text">
            <h2>{BANDS[band].label}</h2>
            <p className="verdict-route">Recommended: {ROUTES[route].action.toLowerCase()}</p>
            <p>{c.rationale}</p>
          </div>
          <div className="verdict-strip-actions">
            {decision ? (
              <span className="chip st-done">
                <Check size={12} strokeWidth={3} />
                Decision logged at {decision.at}
              </span>
            ) : (
              <button type="button" className="btn btn-primary is-large" onClick={approve}>
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
            <StageDetail
              c={c}
              t={t}
              stage={shown}
              status={status[shown]}
              agentFocus={agentFocus}
              edits={edits}
              onEdit={(id, v) => setEdits((e) => ({ ...e, [id]: v }))}
              onRerunFrom={(stage) => {
                run.seek(c.windows.find((w) => w.stage === stage)!.at + 1);
                setPinned(null);
                setEdits({});
                run.play();
              }}
              verdictItems={verdictItems}
            >
              {shown === 'review' ? decisionPanel : null}
            </StageDetail>
          )}
          {panel === 'score' && <ScoreCard score={score} evidenceCount={live.length} phase={phase} coverage={coverage} authenticity={authenticity} />}
          {panel === 'map' && <MapCard c={c} t={t} />}
          {panel === 'claim' && <ClaimCard c={c} />}
          {panel === 'photos' && (
            <section className="card">
              <header className="card-head">
                <h3>Claimant photos</h3>
                <span className="chip">{c.photos.length} files</span>
              </header>
              <PhotoGrid photos={c.photos} t={t} />
            </section>
          )}
          {panel === 'verdict' &&
            (done ? (
              <Report
                c={c}
                evidence={evidence}
                dismissed={dismissed}
                score={score}
                route={route}
                gateTripped={gateTripped}
                tone={tone}
                onToggle={(eid) => setDismissed((d) => (d.includes(eid) ? d.filter((x) => x !== eid) : [...d, eid]))}
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
                <Empty title="The report is assembled when the Judge stops" body={started ? `The run is at step ${stepNo} of ${STAGES.length}.` : 'Start the investigation to build it.'} />
                <div className="empty-actions">
                  <button type="button" className="btn btn-secondary" onClick={run.finish}>
                    Skip to verdict
                  </button>
                </div>
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
