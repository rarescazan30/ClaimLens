import { ArrowRight, Check, ChevronDown, CornerDownRight, Pencil, RefreshCw, TriangleAlert, X } from 'lucide-react';
import { useState } from 'react';
import type { StageStatus } from '../lib/derive';
import { AGENTS, agentName, STAGES } from '../mock/meta';
import type { AgentId, AgentRun, CaseFile, DetailItem, JudgeDecision, StageId } from '../mock/types';
import { AGENT_ICON } from './icons';
import { Empty, PhotoGrid, StatusIcon, VerdictChip } from './ui';

interface Props {
  c: CaseFile;
  t: number;
  stage: StageId;
  status: StageStatus;
  agentFocus: AgentId | null;
  edits: Record<string, string>;
  onEdit: (id: string, value: string) => void;
  onRerunFrom: (stage: StageId) => void;
  verdictItems: DetailItem[];
  children?: React.ReactNode;
}

export function StageDetail(props: Props) {
  const { c, t, stage, status } = props;
  const meta = STAGES.find((s) => s.id === stage)!;
  const win = c.windows.filter((w) => w.stage === stage);
  const first = win[0];

  let body: React.ReactNode;
  if (stage === 'review') {
    body = props.children;
  } else if (status === 'pending' && (!first || t < first.at)) {
    body = <Empty title="Not started yet" body="This step fills in as the run reaches it." />;
  } else if (stage === 'plan') {
    body = <PlanView c={c} t={t} />;
  } else if (stage === 'agents') {
    body = <AgentsView c={c} t={t} focus={props.agentFocus} />;
  } else if (stage === 'judge') {
    body = <JudgeView c={c} t={t} />;
  } else if (stage === 'verdict') {
    body = (
      <>
        <ItemList items={props.verdictItems} t={t} running={status === 'running'} edits={{}} />
        {props.children}
      </>
    );
  } else {
    const items = c.details[stage] ?? [];
    const edited = stage === 'documents' && Object.keys(props.edits).length > 0;
    body = (
      <>
        <ItemList items={items} t={t} running={status === 'running'} edits={props.edits} onEdit={props.onEdit} />
        {edited && (
          <div className="callout c-info">
            <div>
              <p className="callout-title">You corrected a field</p>
              <p>Everything after document parsing was computed with the old value.</p>
            </div>
            <button type="button" className="btn btn-secondary" onClick={() => props.onRerunFrom('documents')}>
              <RefreshCw size={14} />
              Re-run from here
            </button>
          </div>
        )}
        {stage === 'photos' && <PhotoGrid photos={c.photos} t={t} />}
      </>
    );
  }

  return (
    <section className="card detail" aria-live="polite">
      <header className="detail-head">
        <div>
          <p className="eyebrow">
            Step {STAGES.findIndex((s) => s.id === stage) + 1} of {STAGES.length}
          </p>
          <h2>{meta.title}</h2>
          <p className="detail-help">{meta.help}</p>
        </div>
        <span className={`chip st-${status}`}>
          {status === 'running' && <span className="pulse-dot" />}
          {status === 'pending' ? 'Waiting' : status === 'running' ? 'In progress' : status === 'flag' ? 'Flagged' : status === 'requeued' ? 'Back in the queue' : 'Done'}
        </span>
      </header>
      {body}
    </section>
  );
}

function ItemList({
  items,
  t,
  running,
  edits,
  onEdit,
}: {
  items: DetailItem[];
  t: number;
  running: boolean;
  edits: Record<string, string>;
  onEdit?: (id: string, value: string) => void;
}) {
  const shown = items.filter((i) => i.at <= t);
  return (
    <ul className="items">
      {shown.map((i) => (
        <Item key={i.id} item={i} edited={edits[i.id]} onEdit={onEdit} />
      ))}
      {running && shown.length < items.length && (
        <li className="item is-loading" aria-hidden="true">
          <span className="skeleton sk-ico" />
          <span className="skeleton sk-line" />
        </li>
      )}
    </ul>
  );
}

function Item({ item, edited, onEdit }: { item: DetailItem; edited?: string; onEdit?: (id: string, value: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(edited ?? item.value ?? '');
  const [error, setError] = useState('');
  const value = edited ?? item.value;

  const save = () => {
    if (!draft.trim()) {
      setError('Enter a value');
      return;
    }
    onEdit?.(item.id, draft.trim());
    setEditing(false);
  };

  return (
    <li className={`item kind-${item.kind}`}>
      {item.kind === 'check' ? <StatusIcon status={item.status ?? 'ok'} /> : <span className="field-dot" />}
      <div className="item-main">
        <span className="item-label">{item.label}</span>
        {item.note && <span className="item-note">{item.note}</span>}
        {error && <span className="item-error">{error}</span>}
      </div>
      {editing ? (
        <form
          className="item-edit"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <input
            autoFocus
            value={draft}
            aria-label={item.label}
            onChange={(e) => {
              setDraft(e.target.value);
              setError('');
            }}
          />
          <button type="submit" className="icon-btn is-solid" aria-label="Save value">
            <Check size={14} />
          </button>
          <button type="button" className="icon-btn" aria-label="Cancel editing" onClick={() => setEditing(false)}>
            <X size={14} />
          </button>
        </form>
      ) : (
        <div className="item-value">
          {value && <span className={item.kind === 'field' ? 'field-value' : ''}>{value}</span>}
          {edited && <span className="chip c-you">Edited by you</span>}
          {item.confidence !== undefined && !edited && (
            <span className={`conf${item.confidence < 0.9 ? ' is-low' : ''}`} title="Extraction confidence">
              <span className="conf-bar">
                <span style={{ width: `${item.confidence * 100}%` }} />
              </span>
              {Math.round(item.confidence * 100)}%
            </span>
          )}
          {item.editable && onEdit && (
            <button type="button" className="icon-btn" aria-label={`Correct ${item.label}`} onClick={() => setEditing(true)}>
              <Pencil size={13} />
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function PlanView({ c, t }: { c: CaseFile; t: number }) {
  const w = c.windows.find((x) => x.stage === 'plan')!;
  const hyp = c.plan.hypotheses.filter((_, i) => t >= w.at + 300 + i * 320);
  const disp = c.plan.dispatch.filter((_, i) => t >= w.at + 1300 + i * 140);
  return (
    <div className="plan">
      <div>
        <h3>Hypotheses to test</h3>
        <ol className="hyps">
          {hyp.map((h, i) => (
            <li key={h.text}>
              <span className="hyp-n">H{i + 1}</span>
              <span>{h.text}</span>
              {h.critical && <span className="chip c-critical">Critical</span>}
            </li>
          ))}
        </ol>
      </div>
      {disp.length > 0 && (
        <div>
          <h3>Who gets asked what</h3>
          <ul className="dispatch">
            {disp.map((d) => {
              const Icon = AGENT_ICON[d.agent];
              return (
                <li key={d.agent} className={d.skipped ? 'is-skipped' : ''}>
                  <span className="agent-ico">
                    <Icon size={15} />
                  </span>
                  <span className="dispatch-name">{agentName(d.agent)}</span>
                  <span className="dispatch-q">{d.skipped ? `Not dispatched. ${d.skipped}.` : d.question}</span>
                </li>
              );
            })}
          </ul>
          {disp.length === c.plan.dispatch.length && <p className="plan-note">{c.plan.note}</p>}
        </div>
      )}
    </div>
  );
}

function AgentsView({ c, t, focus }: { c: CaseFile; t: number; focus: AgentId | null }) {
  const runs = c.runs.filter((r) => r.at <= t);
  const rounds = [...new Set(runs.map((r) => r.round))].sort((a, b) => b - a);
  const skipped = c.plan.dispatch.filter((d) => d.skipped);
  if (!runs.length) return <Empty title="Agents are about to start" body="Each one answers a single question and reports back." />;
  return (
    <div className="agents">
      {rounds.map((round) => (
        <div key={round}>
          {(rounds.length > 1 || round > 1) && (
            <h3 className="round-title">
              Round {round}
              {round > 1 && <span> · narrower questions from the Judge</span>}
            </h3>
          )}
          <div className="agent-grid">
            {runs
              .filter((r) => r.round === round)
              .sort((a, b) => AGENTS.findIndex((x) => x.id === a.agent) - AGENTS.findIndex((x) => x.id === b.agent))
              .map((r) => (
                <AgentCard key={r.id} run={r} t={t} focused={focus === r.agent} />
              ))}
          </div>
        </div>
      ))}
      {skipped.length > 0 && (
        <p className="skipped-note">
          Not dispatched: {skipped.map((s) => agentName(s.agent)).join(', ')}. The orchestrator judged them irrelevant for this claim type.
        </p>
      )}
    </div>
  );
}

function AgentCard({ run, t, focused }: { run: AgentRun; t: number; focused: boolean }) {
  const Icon = AGENT_ICON[run.agent];
  const done = t >= run.at + run.dur;
  const calls = run.calls.filter((k) => k.at <= t);
  const current = calls[calls.length - 1];
  const [open, setOpen] = useState(focused);
  return (
    <article className={`agent-card${done ? ` v-${run.verdict}` : ' is-running'}${focused ? ' is-focused' : ''}`}>
      <header>
        <span className="agent-ico">
          <Icon size={16} />
        </span>
        <h4>{agentName(run.agent)}</h4>
        {done ? (
          <VerdictChip verdict={run.verdict} />
        ) : (
          <span className="chip st-running">
            <span className="pulse-dot" />
            Working
          </span>
        )}
      </header>
      <p className="agent-finding">{done ? run.finding : current ? `${current.tool}…` : run.question}</p>
      <button type="button" className="agent-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? 'Hide steps' : `Show how (${calls.length} step${calls.length === 1 ? '' : 's'})`}
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="agent-more">
          <p className="agent-q">Asked: {run.question}</p>
          <ul className="calls">
            {calls.map((k) => {
              const kDone = t >= k.at + k.dur;
              return (
                <li key={k.tool} className={kDone ? `k-${k.status}` : 'k-running'}>
                  <span className="call-state">{!kDone ? <span className="spinner" /> : k.status === 'ok' ? <Check size={11} strokeWidth={3} /> : <X size={11} strokeWidth={3} />}</span>
                  <span className="call-tool">{k.tool}</span>
                  <span className="call-sum">{kDone ? k.summary : 'Calling…'}</span>
                </li>
              );
            })}
          </ul>
          {done &&
            run.gaps?.map((g) => (
              <p key={g} className="agent-gap">
                <TriangleAlert size={12} />
                {g}
              </p>
            ))}
        </div>
      )}
    </article>
  );
}

const HYP_TEXT = { confirmed: 'Confirmed', refuted: 'Refuted', open: 'Open', conflict: 'In conflict' } as const;

function JudgeView({ c, t }: { c: CaseFile; t: number }) {
  const shown = c.judge.filter((j) => j.at <= t).reverse();
  return (
    <div className="judge">
      {shown.map((j) => (
        <JudgeCard key={j.round} j={j} t={t} multi={c.judge.length > 1} />
      ))}
    </div>
  );
}

function JudgeCard({ j, t, multi }: { j: JudgeDecision; t: number; multi: boolean }) {
  const k = Math.min(1, (t - j.at) / j.dur);
  const hyps = j.hypotheses.filter((_, i) => k >= 0.12 + i * 0.13);
  const concluded = k >= 0.72;
  return (
    <article className="judge-card">
      {multi && <p className="eyebrow">Round {j.round}</p>}
      <ul className="hyps is-judged">
        {hyps.map((h, i) => (
          <li key={h.text}>
            <span className="hyp-n">H{i + 1}</span>
            <span>{h.text}</span>
            <span className={`chip h-${h.status}`}>{HYP_TEXT[h.status]}</span>
          </li>
        ))}
      </ul>
      {!concluded && (
        <p className="is-working">
          <span className="pulse-dot" />
          Weighing the findings against each hypothesis
        </p>
      )}
      {concluded && j.tension && (
        <div className="callout c-warn">
          <div>
            <p className="callout-title">These two don't fit together</p>
            <p>{j.tension}</p>
          </div>
        </div>
      )}
      {concluded && j.redispatch && (
        <div className="redispatch">
          <h3>Decision: send {j.redispatch.length} agents back</h3>
          <ul>
            {j.redispatch.map((r) => {
              const Icon = AGENT_ICON[r.agent];
              return (
                <li key={r.agent}>
                  <CornerDownRight size={14} className="redispatch-arrow" />
                  <span className="agent-ico">
                    <Icon size={15} />
                  </span>
                  <span className="dispatch-name">{agentName(r.agent)}</span>
                  <span className="dispatch-q">{r.question}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {concluded && j.stop && (
        <div className="callout c-good">
          <div>
            <p className="callout-title">Decision: stop investigating</p>
            <p>{j.stop}</p>
          </div>
        </div>
      )}
      {concluded && (
        <p className="judge-summary">
          <ArrowRight size={14} />
          {j.summary}
        </p>
      )}
    </article>
  );
}
