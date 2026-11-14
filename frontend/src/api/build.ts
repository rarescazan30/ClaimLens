import { AGENTS, agentName, isAgent, RULE_LABEL, TYPE_LABEL } from '../lib/meta';
import type {
  AgentId,
  AgentRun,
  ApiClaimDetail,
  ApiClaimRow,
  ApiEvidence,
  ApiScore,
  ApiTraceStep,
  CaseFile,
  ClaimType,
  DetailItem,
  Evidence,
  JudgeDecision,
  LatLon,
  MapSpec,
  Mark,
  Photo,
  Question,
  QueueCase,
  ScoreStep,
  StageId,
  StageWindow,
  Status,
  ToolCall,
} from '../lib/types';
import { photoUrl } from './client';

/**
 * Turns what the backend returns (claim detail + trace) into the CaseFile the screens draw.
 * Nothing here invents data: every value comes from the backend, only the layout in time is ours.
 *
 * Time. The screens are driven by a clock in ms.
 *  - A run that took real time (live keys) is laid out on the backend's own timestamps.
 *  - A run answered from saved responses finishes in under a second. Nobody could follow that,
 *    so it is laid out with even pacing instead (`paced: true`). The order of steps is unchanged.
 *  See layout() below.
 */

/** Stand-in for "not finished yet" in a duration. */
export const OPEN = 1e12;
/** Below this real length a finished run is replayed with even pacing. */
const PACED_BELOW_MS = 15_000;

const PACE = { lead: 1000, rules: 1500, plan: 2400, agentGap: 180, step: 650, emptyRun: 900, score: 500, judge: 3400, final: 1600, other: 300 };

// ---------------------------------------------------------------- formatting

export const fmtDate = (iso?: string | null) => {
  if (!iso) return 'Not stated';
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

const fmtDateTime = (iso?: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

const placeOf = (address: string) => {
  const parts = address.split(',').map((s) => s.trim()).filter(Boolean);
  return parts.length > 1 ? parts.slice(1).join(', ') : address;
};

const lagOf = (event: string, notified: string | null) => {
  if (!notified) return 'Notification date not stated';
  const days = Math.round((Date.parse(notified.slice(0, 10)) - Date.parse(event.slice(0, 10))) / 86_400_000);
  if (Number.isNaN(days)) return '';
  return days <= 0 ? 'Filed on the day of the event' : `Filed ${days} day${days === 1 ? '' : 's'} after the event`;
};

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
const point = (v: unknown): LatLon | undefined => {
  const p = v as { lat?: unknown; lon?: unknown } | null;
  return p && typeof p.lat === 'number' && typeof p.lon === 'number' ? { lat: p.lat, lon: p.lon } : undefined;
};
const findingMap = (e?: ApiEvidence) => Object.fromEntries((e?.findings ?? []).map((f) => [f.metric, f.value])) as Record<string, unknown>;

/** A few words for what an agent found, built from its measured values (never from model text). */
export function headline(e: ApiEvidence, type: ClaimType, photoCount: number, brief = false): string {
  const f = findingMap(e);
  switch (e.agent) {
    case 'meteo': {
      const gust = num(f.wind_gusts_event_day) ?? num(f.wind_gusts_10m_max);
      const rain = num(f.precipitation_24h_max) ?? num(f.precipitation_event_day);
      if (type === 'storm' && gust !== undefined) return `${gust} km/h gusts`;
      if (rain !== undefined) return brief ? `${rain} mm in 24 h` : `${rain} mm of rain in 24 h`;
      if (gust !== undefined) return `${gust} km/h gusts`;
      break;
    }
    case 'satellite': {
      const d = num(f.distance_to_flood_edge_m);
      if (f.inside_flood_extent === true) return brief ? 'Inside the flood' : 'Inside the mapped flood';
      if (f.inside_flood_extent === false) return d !== undefined ? `${Math.round(d)} m outside the ${brief ? '' : 'mapped '}flood` : 'Outside the mapped flood';
      break;
    }
    case 'risk_zones': {
      const diff = num(f.elevation_diff_m);
      const d = num(f.distance_to_water_m);
      if (diff !== undefined) return `${brief ? '' : 'House '}${Math.abs(diff)} m ${diff >= 0 ? 'above' : 'below'} the flood${brief ? '' : ' edge'}`;
      if (d !== undefined) return `${Math.round(d)} m to ${typeof f.water_name === 'string' ? f.water_name : 'the nearest water'}`;
      break;
    }
    case 'news': {
      const n = num(f.reports_confirmed);
      if (n !== undefined) return `${n} press report${n === 1 ? '' : 's'}`;
      break;
    }
    case 'street_view':
      if (typeof f.pre_event_image_date === 'string') return `Street image from ${f.pre_event_image_date}`;
      if (!e.findings.length) return 'No street imagery';
      break;
    case 'photo_forensics':
      if (f.exact_copy_before_event === true) return 'Photo published before the event';
      if (photoCount === 0) return 'No photos on file';
      return `${photoCount} photo${photoCount === 1 ? '' : 's'} checked`;
  }
  return e.verdict === 'supports' ? 'Supports the claim' : e.verdict === 'contradicts' ? 'Contradicts the claim' : 'Inconclusive';
}

// ---------------------------------------------------------------- trace parsing

type Kind = 'rules' | 'plan' | 'dispatch' | 'agent' | 'score' | 'judge' | 'question' | 'final' | 'error' | 'other';
interface Parsed {
  step: ApiTraceStep;
  kind: Kind;
  round: number;
  agent?: AgentId;
}

/** Step ids, as documented in demo/mock/README.md. */
function parse(step: ApiTraceStep): Parsed {
  const id = step.step_id;
  if (id === 'rules' || id === 'plan' || id === 'final') return { step, kind: id, round: 0 };
  if (id.startsWith('error.')) return { step, kind: 'error', round: 0 };
  const m = /^r(\d+)\.(dispatch|score|judge|question|final)$/.exec(id);
  if (m) return { step, kind: m[2] as Kind, round: Number(m[1]) };
  const a = /^r(\d+)\.([a-z_]+)\.\d+$/.exec(id);
  if (a && isAgent(a[2])) return { step, kind: 'agent', round: Number(a[1]), agent: a[2] };
  return { step, kind: 'other', round: 0 };
}

const stamp = (s: ApiTraceStep) => Date.parse(s.ended_at ?? s.started_at);

/**
 * A time in ms for every step.
 *
 * The trace is cut into runs: the first investigation, then one run per question the adjuster asked later
 * (which can be minutes or days apart). Runs are laid end to end, so idle time between them never shows.
 * Within a run: the backend's own timestamps if it took real time, even pacing if it was too fast to watch.
 * `paced[i]` says which of the two step i got.
 */
function layout(steps: Parsed[], live: boolean, lead: number): { T: number[]; paced: boolean[] } {
  const T: number[] = [];
  const paced: boolean[] = [];
  const runs: Parsed[][] = [];
  for (const p of steps) {
    if (p.kind === 'question' || !runs.length) runs.push([]);
    runs[runs.length - 1].push(p);
  }
  let cursor = lead;
  runs.forEach((run, r) => {
    const t0 = Math.min(...run.map((p) => Date.parse(p.step.started_at)));
    const span = Math.max(...run.map((p) => stamp(p.step))) - t0;
    const fast = span < PACED_BELOW_MS && !(live && r === runs.length - 1);
    const start = cursor;
    if (!fast) {
      for (const p of run) {
        const t = start + Math.max(0, stamp(p.step) - t0);
        T.push(t);
        paced.push(false);
        cursor = Math.max(cursor, t);
      }
      return;
    }
    let roundStart = cursor;
    let roundEnd = cursor;
    let order: string[] = [];
    const count = new Map<string, number>();
    for (const p of run) {
      let t: number;
      switch (p.kind) {
        case 'rules':
          t = cursor += PACE.rules;
          break;
        case 'plan':
          t = cursor += PACE.plan;
          break;
        case 'question':
          t = cursor;
          break;
        case 'dispatch':
          roundStart = cursor;
          roundEnd = cursor + PACE.emptyRun;
          order = [];
          count.clear();
          t = cursor;
          break;
        case 'agent': {
          const key = p.agent!;
          if (!order.includes(key)) order.push(key);
          const k = (count.get(key) ?? 0) + 1;
          count.set(key, k);
          t = roundStart + order.indexOf(key) * PACE.agentGap + k * PACE.step;
          roundEnd = Math.max(roundEnd, t);
          break;
        }
        case 'score':
          t = cursor = roundEnd + PACE.score;
          break;
        case 'judge':
          t = cursor += PACE.judge;
          break;
        case 'final':
          t = cursor += PACE.final;
          break;
        default:
          t = cursor += PACE.other;
      }
      T.push(t);
      paced.push(true);
    }
  });
  return { T, paced };
}

// ---------------------------------------------------------------- the case file

export function buildCase(d: ApiClaimDetail, trace: ApiTraceStep[]): CaseFile {
  const { claim, policy } = d;
  const live = claim.status === 'investigating';
  const steps = trace.map(parse);
  const lead = PACE.lead;
  const { T, paced: pacedAt } = layout(steps, live, lead);
  // True when the latest run was laid out with even pacing: the screen then plays it back once it is over.
  const paced = pacedAt.length > 0 && pacedAt[pacedAt.length - 1];
  const typeLabel = TYPE_LABEL[claim.damage_type] ?? claim.damage_type;
  const photoNames = claim.photos ?? [];

  // ---- stage windows: each stage runs from the end of the one before it to its own closing step
  const windows: StageWindow[] = [{ stage: 'intake', at: 0, dur: lead }];
  let prev = lead;
  const close = (stage: StageId, end: number, round?: number) => {
    windows.push({ stage, round: round || undefined, at: prev, dur: Math.max(end - prev, 1) });
    prev = Math.max(end, prev + 1);
  };
  let next: { stage: StageId; round?: number } = { stage: 'policy' };
  let lastRound = 0;
  let error: string | undefined;
  steps.forEach((p, i) => {
    lastRound = Math.max(lastRound, p.round);
    if (p.kind === 'rules') {
      close('policy', T[i]);
      next = { stage: 'plan' };
    } else if (p.kind === 'plan') {
      close('plan', T[i]);
      next = { stage: 'agents', round: 1 };
    } else if (p.kind === 'question' || p.kind === 'dispatch') {
      next = { stage: 'agents', round: p.kind === 'dispatch' ? p.round : p.round + 1 };
    } else if (p.kind === 'score') {
      close('agents', T[i], p.round);
      next = { stage: 'judge', round: p.round };
    } else if (p.kind === 'judge') {
      close('judge', T[i], p.round);
      next = p.step.outputs.action === 'redispatch' ? { stage: 'agents', round: p.round + 1 } : { stage: 'verdict' };
    } else if (p.kind === 'final') {
      close('verdict', T[i]);
      next = { stage: 'agents', round: lastRound + 1 };
    } else if (p.kind === 'error') {
      close('verdict', T[i]);
      error = p.step.summary;
      next = { stage: 'agents', round: lastRound + 1 };
    }
  });
  if (live) windows.push({ stage: next.stage, round: next.round, at: prev, dur: OPEN });
  const edge = prev;
  const duration = live ? OPEN : prev;

  // ---- agent runs: one per agent per round, from trace steps and/or the evidence row
  const evidenceOf = (agent: string, round: number) => d.evidence.find((e) => e.agent === agent && e.round === round);
  const dispatches = steps.map((p, i) => ({ p, t: T[i], even: pacedAt[i] })).filter((x) => x.p.kind === 'dispatch');
  const runs: AgentRun[] = [];
  const runEnd = new Map<string, number>();
  for (const { p: dp, t: dt, even } of dispatches) {
    const asked = ((dp.step.outputs.agents as { agent: string; question: string | null }[] | undefined) ?? []).filter((a) => isAgent(a.agent));
    const seen = steps.filter((p) => p.kind === 'agent' && p.round === dp.round).map((p) => p.agent!);
    const fromEvidence = d.evidence.filter((e) => e.round === dp.round).map((e) => e.agent);
    const agents = [...new Set<AgentId>([...asked.map((a) => a.agent as AgentId), ...seen, ...fromEvidence])];
    agents.forEach((agent, idx) => {
      const mine = steps.map((p, i) => ({ p, t: T[i] })).filter((x) => x.p.kind === 'agent' && x.p.round === dp.round && x.p.agent === agent);
      const ev = evidenceOf(agent, dp.round);
      const last = mine[mine.length - 1];
      const concluded = !!ev || (last && 'verdict' in last.p.step.outputs) || !live;
      const at = even ? (mine.length ? mine[0].t - PACE.step : dt + idx * PACE.agentGap) : dt;
      const end = last ? last.t : even ? at + PACE.emptyRun : at + 1;
      const calls: ToolCall[] = [];
      const body = mine.filter((x) => !('verdict' in x.p.step.outputs));
      for (let i = 0; i < body.length; i++) {
        const { p: sp, t: st } = body[i];
        const answer = body[i + 1];
        const isAnswer = answer && answer.p.step.type === 'observation' && ('preview' in answer.p.step.outputs || 'error' in answer.p.step.outputs);
        if (sp.step.type === 'tool_call' && isAnswer) {
          const failed = answer.p.step.status === 'failed';
          calls.push({
            id: sp.step.step_id,
            at: st,
            dur: Math.max(answer.t - st, 1),
            tool: sp.step.sources[0] ?? sp.step.summary,
            summary: failed ? answer.p.step.summary : 'Answered',
            status: failed ? 'fail' : 'ok',
          });
          i++;
        } else {
          calls.push({
            id: sp.step.step_id,
            at: st,
            dur: 1,
            tool: sp.step.type === 'tool_call' ? (sp.step.sources[0] ?? sp.step.summary) : '',
            summary: sp.step.type === 'tool_call' ? '' : sp.step.summary,
            status: sp.step.status === 'failed' ? 'fail' : 'ok',
          });
        }
      }
      const question =
        asked.find((a) => a.agent === agent)?.question ?? ev?.hypothesis ?? d.hypotheses.find((h) => h.agents.includes(agent))?.text ?? '';
      runs.push({
        id: `r${dp.round}.${agent}`,
        agent,
        round: dp.round,
        at,
        dur: concluded ? Math.max(end - at, 1) : OPEN,
        question,
        verdict: ev?.verdict ?? ((last?.p.step.outputs.verdict as AgentRun['verdict'] | undefined) ?? 'inconclusive'),
        finding: ev?.reasoning_steps[0] ?? ev?.gaps[0] ?? last?.p.step.summary ?? 'No finding recorded.',
        short: ev ? headline(ev, claim.damage_type, photoNames.length, true) : '',
        calls,
        gaps: ev?.gaps ?? [],
      });
      if (concluded) runEnd.set(`${dp.round}.${agent}`, Math.max(end, at + 1));
    });
  }
  runs.sort((a, b) => a.at - b.at || AGENTS.findIndex((x) => x.id === a.agent) - AGENTS.findIndex((x) => x.id === b.agent));
  const knownAt = (agent: string, round: number) => runEnd.get(`${round}.${agent}`) ?? edge;

  // ---- evidence
  const evidence: Evidence[] = d.evidence.map((e) => ({
    id: e.id,
    agent: e.agent,
    round: e.round,
    title: headline(e, claim.damage_type, photoNames.length),
    detail: e.reasoning_steps[0] ?? e.gaps[0] ?? '',
    source: [...new Set(e.findings.map((f) => f.source))].slice(0, 2).join(' · ') || (AGENTS.find((a) => a.id === e.agent)?.source ?? ''),
    verdict: e.verdict,
    rejected: e.rejected_by_adjuster,
    at: knownAt(e.agent, e.round),
  }));

  // ---- score: always the backend's number. One entry per time the backend computed it.
  const scores: ScoreStep[] = steps
    .map((p, i) => ({ p, t: T[i] }))
    .filter((x) => x.p.kind === 'score' && typeof x.p.step.outputs.score === 'number')
    .map((x) => {
      const o = x.p.step.outputs as unknown as ApiScore;
      return { score: o.score, band: o.band, recommendation: o.recommendation, contributions: o.contributions ?? [], gates: o.gates ?? [], round: x.p.round, at: x.t };
    });
  if (d.score && !live) {
    // The stored score is the truth: it already reflects findings the adjuster set aside.
    if (scores.length) scores[scores.length - 1] = { ...scores[scores.length - 1], ...d.score };
    else scores.push({ ...d.score, round: 0, at: edge });
  }

  // ---- judge
  const hyps = d.hypotheses.length ? d.hypotheses : ((steps.find((p) => p.kind === 'plan')?.step.outputs.hypotheses as ApiClaimDetail['hypotheses'] | undefined) ?? []);
  const judge: JudgeDecision[] = steps
    .map((p, i) => ({ p, t: T[i] }))
    .filter((x) => x.p.kind === 'judge')
    .map((x) => {
      const o = x.p.step.outputs as { marks?: Record<string, Mark>; tensions?: string[]; action?: string; redispatch?: { agent: string; question: string }[]; stop_reason?: string };
      const scoreAt = scores.find((s) => s.round === x.p.round)?.at;
      const at = scoreAt !== undefined && scoreAt < x.t ? scoreAt : x.t - 1;
      const back = o.action === 'redispatch' ? (o.redispatch ?? []).filter((r) => isAgent(r.agent)).map((r) => ({ agent: r.agent as AgentId, question: r.question })) : [];
      return {
        round: x.p.round,
        at,
        dur: x.t - at,
        hypotheses: hyps.map((h) => ({ id: h.id, text: h.text, mark: o.marks?.[h.id] ?? 'inconclusive' })),
        tensions: o.tensions ?? [],
        redispatch: back.length ? back : undefined,
        stop: o.action === 'stop' ? o.stop_reason || 'The Judge stopped the investigation.' : undefined,
        summary: back.length ? `Sent ${back.length} agent${back.length === 1 ? '' : 's'} back with narrower questions.` : `Stopped. ${o.stop_reason ?? ''}`.trim(),
      };
    });

  // ---- plan
  const first = dispatches.find((x) => x.p.round === 1);
  const firstAgents = ((first?.p.step.outputs.agents as { agent: string; question: string | null }[] | undefined) ?? []).filter((a) => isAgent(a.agent));
  const plan = {
    hypotheses: hyps.map((h) => ({ id: h.id, text: h.text, critical: h.critical })),
    dispatch: [
      ...firstAgents.map((a) => ({
        agent: a.agent as AgentId,
        question: a.question ?? hyps.filter((h) => h.agents.includes(a.agent)).map((h) => h.id).join(', '),
      })),
      ...d.not_relevant_agents.filter(isAgent).map((agent) => ({ agent, skipped: true })),
    ],
  };

  // ---- step details
  const facts: [string, string][] = [
    ['Claim number', claim.id],
    ['Policyholder', policy?.holder_name ?? 'Not on file'],
    ['Loss address', claim.address],
    ['Declared event', `${typeLabel}, ${fmtDate(claim.event_date)}`],
    ['Notified', fmtDate(claim.notified_at)],
    ['Amount claimed', claim.amount_claimed != null ? `${claim.amount_claimed.toLocaleString('en-US')} RON` : 'Not stated'],
    ['Photos attached', String(photoNames.length)],
  ];
  const policyWindow = windows.find((w) => w.stage === 'policy');
  const details: Partial<Record<StageId, DetailItem[]>> = {
    intake: facts.map(([label, value], i) => ({ id: `i${i}`, at: ((i + 1) * lead) / (facts.length + 1), label, value, status: 'info' as Status })),
    policy: policyWindow
      ? d.rule_flags.map((f, i) => ({
          id: f.rule,
          at: policyWindow.dur >= OPEN ? policyWindow.at : policyWindow.at + ((i + 1) * policyWindow.dur) / (d.rule_flags.length + 1),
          label: RULE_LABEL[f.rule] ?? f.rule.replace(/_/g, ' '),
          note: f.reason,
          status: (f.passed ? 'ok' : 'fail') as Status,
        }))
      : [],
  };
  const rulesPassed = d.rule_flags.every((f) => f.passed);

  // ---- photos: real files, with the forensic agent's per-photo checks
  const forensic = [...d.evidence].reverse().find((e) => e.agent === 'photo_forensics');
  const photos: Photo[] = photoNames.map((name) => {
    const base = name.split('/').pop() ?? name;
    const notes: string[] = [];
    let status: Status = 'ok';
    const worse = (s: Status) => {
      if (s === 'fail' || (s === 'flag' && status !== 'fail')) status = s;
    };
    for (const f of forensic?.findings ?? []) {
      if (!f.metric.startsWith(`${base}:`)) continue;
      const check = f.metric.slice(base.length + 1);
      const v = f.value;
      if (check === 'unreadable') (notes.push('File could not be read'), worse('flag'));
      else if (check === 'exif_missing') (notes.push('No capture date or location in the file'), worse('flag'));
      else if (check === 'exif_date') notes.push(`Taken ${fmtDate(String(v))}`);
      else if (check === 'exif_days_before_event') (notes.push(v === 0 ? 'Taken on the day of the event' : `Taken ${v} days before the event`), Number(v) > 0 && worse('fail'));
      else if (check === 'exif_days_after_event') notes.push(`Taken ${v} days after the event`);
      else if (check === 'exif_distance_to_address_km') notes.push(`Taken ${v} km from the address`);
      else if (check === 'copy_in_other_claim') v === true && (notes.push('Same photo found in an earlier claim'), worse('fail'));
      else if (check === 'shows_declared_damage') v === false ? (notes.push('Does not show the declared damage'), worse('flag')) : v === true && notes.push('Shows the declared damage');
      else if (check === 'looks_generated') v === true && (notes.push('Looks computer-generated'), worse('flag'));
      else if (check === 'description') notes.push(String(v));
      else if (check === 'web_matches') Number(v) > 0 && (notes.push(`${v} matching page${v === 1 ? '' : 's'} on the web`), worse('flag'));
      else if (check === 'first_seen') (notes.push(`First published ${fmtDate(String(v))}`), String(v) < claim.event_date && worse('fail'));
      else notes.push(`${check.replace(/_/g, ' ')}: ${String(v)}`);
    }
    if (!notes.length) status = 'info';
    return { name: base, url: photoUrl(name), status, notes: notes.length ? notes : ['No checks recorded for this photo'], at: forensic ? knownAt('photo_forensics', forensic.round) : OPEN };
  });

  // ---- map: only when the backend has a mapped flood for this claim
  let map: MapSpec | undefined;
  const sats = d.evidence.filter((e) => e.agent === 'satellite');
  const sat = findingMap(sats[sats.length - 1]);
  if (claim.lat != null && claim.lon != null && typeof sat.flood_extent_geojson_url === 'string' && sats.length) {
    const risks = d.evidence.filter((e) => e.agent === 'risk_zones');
    const risk = findingMap(risks[risks.length - 1]);
    const elevFrom = risks.find((e) => e.findings.some((f) => f.metric === 'elevation_diff_m'));
    const water = point(risk.nearest_water_point);
    map = {
      house: { lat: claim.lat, lon: claim.lon },
      activation: String(sat.activation ?? ''),
      mapDate: typeof sat.map_date === 'string' ? sat.map_date : undefined,
      inside: sat.inside_flood_extent === true,
      distanceM: num(sat.distance_to_flood_edge_m),
      edge: point(sat.nearest_edge_point),
      zoneAt: knownAt('satellite', sats[0].round),
      water: water ? { ...water, name: typeof risk.water_name === 'string' ? risk.water_name : undefined, distanceM: num(risk.distance_to_water_m) } : undefined,
      elevationDiffM: num(risk.elevation_diff_m),
      elevationAt: elevFrom ? knownAt('risk_zones', elevFrom.round) : undefined,
    };
  }

  const lastJudge = judge[judge.length - 1];
  const finalStep = [...steps].reverse().find((p) => p.kind === 'final');
  const questions: Question[] = steps
    .map((p, i) => ({ p, t: T[i] }))
    .filter((x) => x.p.kind === 'question')
    .map((x) => ({
      text: String(x.p.step.outputs.question ?? x.p.step.summary),
      agent: isAgent(String(x.p.step.outputs.agent)) ? (x.p.step.outputs.agent as AgentId) : undefined,
      round: x.p.round + 1,
      at: x.t,
    }));

  return {
    id: claim.id,
    status: claim.status,
    claimant: policy?.holder_name ?? 'Policyholder not on file',
    type: claim.damage_type,
    typeLabel,
    place: placeOf(claim.address),
    address: claim.address,
    eventDate: fmtDate(claim.event_date),
    filed: fmtDate(claim.notified_at),
    lag: lagOf(claim.event_date, claim.notified_at),
    policy: policy ? `${policy.product} · ${policy.id}` : claim.policy_id,
    claimed: claim.amount_claimed != null ? `${claim.amount_claimed.toLocaleString('en-US')} RON` : 'Amount not stated',
    description: claim.description ?? '',
    duration,
    edge,
    paced,
    windows,
    flags: rulesPassed ? [] : ['policy'],
    details,
    plan,
    runs,
    evidence,
    scores,
    judge,
    photos,
    map,
    rulesPassed,
    rationale: lastJudge?.tensions.slice(0, 2).join(' ') || finalStep?.step.summary || '',
    decision: claim.decision && claim.outcome ? { kind: claim.decision, outcome: claim.outcome, reason: claim.decision_reason ?? undefined, at: fmtDateTime(claim.decided_at) } : undefined,
    questions,
    error,
  };
}

// ---------------------------------------------------------------- the queue

/** One queue row. GET /claims has no claimant or description, so they come from the claim's detail. */
export function buildQueueRow(row: ApiClaimRow, d?: ApiClaimDetail): QueueCase {
  const latest = new Map<string, ApiEvidence>();
  for (const e of d?.evidence ?? []) if (!e.rejected_by_adjuster) latest.set(e.agent, e);
  const photoCount = d?.claim.photos?.length ?? 0;
  const signals = [...latest.values()]
    .filter((e) => e.verdict !== 'inconclusive')
    .sort((a, b) => b.strength * b.data_quality - a.strength * a.data_quality)
    .slice(0, 3)
    .map((e) => `${agentName(e.agent)}: ${headline(e, row.damage_type, photoCount)}`);
  return {
    id: row.id,
    claimant: d?.policy?.holder_name ?? 'Policyholder not on file',
    type: row.damage_type,
    typeLabel: TYPE_LABEL[row.damage_type] ?? row.damage_type,
    place: placeOf(row.address),
    filed: fmtDate(d?.claim.notified_at ?? row.created_at),
    description: d?.claim.description ?? '',
    status: row.status,
    score: row.score ?? undefined,
    band: row.band ?? undefined,
    outcome: row.outcome ?? row.recommendation ?? undefined,
    decided: row.status === 'decided',
    signals,
  };
}
