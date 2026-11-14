import { ArrowRight, Check, ChevronDown, CornerDownRight, TriangleAlert, X } from 'lucide-react';
import { useState } from 'react';
import type { StageStatus } from '../lib/derive';
import { AGENTS, agentName, MARK_TEXT, nr, STAGES } from '../lib/meta';
import type { AgentId, AgentRun, CaseFile, DetailItem, JudgeDecision, StageId } from '../lib/types';
import { AGENT_ICON } from './icons';
import { Empty, StatusIcon, VerdictChip } from './ui';

interface Props {
  c: CaseFile;
  t: number;
  stage: StageId;
  status: StageStatus;
  agentFocus: AgentId | null;
  verdictItems: DetailItem[];
  children?: React.ReactNode;
}

export function StageDetail(props: Props) {
  const { c, t, stage, status } = props;
  const meta = STAGES.find((s) => s.id === stage)!;
  const first = c.windows.find((w) => w.stage === stage);

  let body: React.ReactNode;
  if (stage === 'review') {
    body = props.children;
  } else if (status === 'pending' && (!first || t < first.at)) {
    body = <Empty title="Neînceput" body="Informațiile apar când investigația ajunge la acest pas." />;
  } else if (stage === 'plan') {
    body = <PlanView c={c} t={t} />;
  } else if (stage === 'agents') {
    body = <AgentsView c={c} t={t} focus={props.agentFocus} />;
  } else if (stage === 'judge') {
    body = <JudgeView c={c} t={t} />;
  } else if (stage === 'verdict') {
    body = (
      <>
        <ItemList items={props.verdictItems} t={t} running={status === 'running'} />
        {props.children}
      </>
    );
  } else {
    body = <ItemList items={c.details[stage] ?? []} t={t} running={status === 'running'} />;
  }

  return (
    <section className="card detail" aria-live="polite">
      <header className="detail-head">
        <div>
          <p className="eyebrow">
            Pasul {STAGES.findIndex((s) => s.id === stage) + 1} din {STAGES.length}
          </p>
          <h2>{meta.title}</h2>
          <p className="detail-help">{meta.help}</p>
        </div>
        <span className={`chip st-${status}`}>
          {status === 'running' && <span className="pulse-dot" />}
          {status === 'pending' ? 'În așteptare' : status === 'running' ? 'În curs' : status === 'flag' ? 'Semnalat' : status === 'requeued' ? 'Reluat' : 'Finalizat'}
        </span>
      </header>
      {body}
    </section>
  );
}

function ItemList({ items, t, running }: { items: DetailItem[]; t: number; running: boolean }) {
  const shown = items.filter((i) => i.at <= t);
  return (
    <ul className="items">
      {shown.map((i) => (
        <li key={i.id} className="item kind-check">
          <StatusIcon status={i.status ?? 'ok'} />
          <div className="item-main">
            <span className="item-label">{i.label}</span>
            {i.note && <span className="item-note">{i.note}</span>}
          </div>
          {i.value && (
            <div className="item-value">
              <span>{i.value}</span>
            </div>
          )}
        </li>
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

function PlanView({ c, t }: { c: CaseFile; t: number }) {
  const w = c.windows.find((x) => x.stage === 'plan');
  if (!w) return <Empty title="Se întocmește planul" body="Sistemul stabilește ce trebuie verificat." />;
  // The plan arrives in one piece at the end of this step; the items appear in turn when the step is replayed.
  const k = w.dur > 60_000 ? 0 : Math.min(1, (t - w.at) / w.dur);
  const total = c.plan.hypotheses.length + c.plan.dispatch.length;
  const count = t >= w.at + w.dur ? total : Math.floor(k * total);
  const hyp = c.plan.hypotheses.slice(0, count);
  const disp = c.plan.dispatch.slice(0, Math.max(0, count - c.plan.hypotheses.length));
  if (!hyp.length) return <Empty title="Se întocmește planul" body="Sistemul stabilește ce trebuie verificat." />;
  const asked = c.plan.dispatch.filter((d) => !d.skipped).length;
  return (
    <div className="plan">
      <div>
        <h3>Ipoteze de verificat</h3>
        <ol className="hyps">
          {hyp.map((h) => (
            <li key={h.id}>
              <span className="hyp-n">{h.id}</span>
              <span>{h.text}</span>
              {h.critical && <span className="chip c-critical">Esențială</span>}
            </li>
          ))}
        </ol>
      </div>
      {disp.length > 0 && (
        <div>
          <h3>Agenți trimiși</h3>
          <ul className="dispatch">
            {disp.map((d) => {
              const Icon = AGENT_ICON[d.agent];
              return (
                <li key={d.agent} className={d.skipped ? 'is-skipped' : ''}>
                  <span className="agent-ico">
                    <Icon size={15} />
                  </span>
                  <span className="dispatch-name">{agentName(d.agent)}</span>
                  <span className="dispatch-q">{d.skipped ? 'Nu a fost trimis: nu este relevant pentru acest tip de daună.' : `Verifică ${d.question}`}</span>
                </li>
              );
            })}
          </ul>
          {disp.length === c.plan.dispatch.length && (
            <p className="plan-note">
              La o daună prin {c.typeLabel.toLowerCase()} se trimit {asked} din cei {AGENTS.length} agenți în prima rundă.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function AgentsView({ c, t, focus }: { c: CaseFile; t: number; focus: AgentId | null }) {
  const runs = c.runs.filter((r) => r.at <= t);
  const rounds = [...new Set(runs.map((r) => r.round))].sort((a, b) => b - a);
  const skipped = c.plan.dispatch.filter((d) => d.skipped);
  if (!runs.length) return <Empty title="Agenții pornesc" body="Fiecare răspunde la o singură întrebare." />;
  const asked = c.questions.filter((q) => q.at <= t);
  return (
    <div className="agents">
      {rounds.map((round) => (
        <div key={round}>
          {(rounds.length > 1 || round > 1) && (
            <h3 className="round-title">
              Runda {round}
              {round > 1 && <span> · {asked.some((q) => q.round === round) ? 'întrebarea dumneavoastră' : 'întrebări mai precise de la Arbitru'}</span>}
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
          Nu au fost trimiși: {skipped.map((s) => agentName(s.agent)).join(', ')}, pentru că nu sunt relevanți la acest tip de daună.
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
            Lucrează
          </span>
        )}
      </header>
      <p className="agent-finding">{done ? run.finding : current ? `${current.tool || current.summary}…` : run.question}</p>
      {(calls.length > 0 || (done && run.gaps.length > 0)) && (
        <button type="button" className="agent-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Ascundeți pașii' : calls.length ? `Vedeți pașii (${calls.length})` : 'Ce date lipsesc'}
          <ChevronDown size={14} />
        </button>
      )}
      {open && (
        <div className="agent-more">
          {run.question && <p className="agent-q">Întrebare: {run.question}</p>}
          <ul className="calls">
            {calls.map((k) => {
              const kDone = t >= k.at + k.dur;
              return (
                <li key={k.id} className={kDone ? `k-${k.status}` : 'k-running'}>
                  <span className="call-state">{!kDone ? <span className="spinner" /> : k.status === 'ok' ? <Check size={11} strokeWidth={3} /> : <X size={11} strokeWidth={3} />}</span>
                  {k.tool && <span className="call-tool">{k.tool}</span>}
                  <span className="call-sum">{kDone ? k.summary : 'Se așteaptă răspunsul…'}</span>
                </li>
              );
            })}
          </ul>
          {done &&
            run.gaps.map((g) => (
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

function JudgeView({ c, t }: { c: CaseFile; t: number }) {
  const shown = c.judge.filter((j) => j.at <= t).reverse();
  if (!shown.length)
    return (
      <p className="is-working">
        <span className="pulse-dot" />
        Arbitrul compară rezultatele cu fiecare ipoteză
      </p>
    );
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
  const n = j.hypotheses.length || 1;
  const hyps = j.hypotheses.filter((_, i) => k >= 0.1 + (i * 0.55) / n);
  const concluded = k >= 0.72;
  return (
    <article className="judge-card">
      {multi && <p className="eyebrow">Runda {j.round}</p>}
      <ul className="hyps is-judged">
        {hyps.map((h) => (
          <li key={h.id}>
            <span className="hyp-n">{h.id}</span>
            <span>{h.text}</span>
            <span className={`chip h-${h.mark}`}>{MARK_TEXT[h.mark]}</span>
          </li>
        ))}
      </ul>
      {!concluded && (
        <p className="is-working">
          <span className="pulse-dot" />
          Arbitrul compară rezultatele cu fiecare ipoteză
        </p>
      )}
      {concluded && j.tensions.length > 0 && (
        <div className="callout c-warn">
          <div>
            <p className="callout-title">Ce nu se potrivește</p>
            {j.tensions.map((x) => (
              <p key={x}>{x}</p>
            ))}
          </div>
        </div>
      )}
      {concluded && j.redispatch && (
        <div className="redispatch">
          <h3>
            Decizie: {j.redispatch.length === 1 ? 'un agent verifică' : `${nr(j.redispatch.length, 'agent', 'agenți')} verifică`} din nou
          </h3>
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
            <p className="callout-title">Decizie: investigația se încheie</p>
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
