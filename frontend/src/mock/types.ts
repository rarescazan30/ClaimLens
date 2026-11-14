export type StageId =
  | 'intake'
  | 'client'
  | 'documents'
  | 'policy'
  | 'photos'
  | 'plan'
  | 'agents'
  | 'judge'
  | 'verdict'
  | 'review';

export type AgentId = 'weather' | 'satellite' | 'streetview' | 'news' | 'risk' | 'forensics';
export type Verdict = 'supports' | 'contradicts' | 'inconclusive';
export type Status = 'ok' | 'flag' | 'fail' | 'info';
export type Band = 'very-likely' | 'likely' | 'uncertain' | 'unlikely';
export type Route = 'fast-track' | 'standard' | 'investigate';
export type ClaimType = 'flood' | 'wind' | 'landslide' | 'snow';

/** A stretch of the run timeline during which a stage is active. `at` and `dur` are ms offsets. */
export interface StageWindow {
  stage: StageId;
  round?: number;
  at: number;
  dur: number;
}

export interface DetailItem {
  id: string;
  at: number;
  kind: 'check' | 'field';
  label: string;
  value?: string;
  status?: Status;
  confidence?: number;
  note?: string;
  editable?: boolean;
}

export interface ToolCall {
  at: number;
  dur: number;
  tool: string;
  summary: string;
  status: 'ok' | 'fail';
}

export interface AgentRun {
  id: string;
  agent: AgentId;
  round: number;
  at: number;
  dur: number;
  question: string;
  verdict: Verdict;
  /** Full finding sentence shown on the agent card. */
  finding: string;
  /** Few-word version shown on the pipeline lane. */
  short: string;
  calls: ToolCall[];
  gaps?: string[];
}

export interface Evidence {
  id: string;
  agent: AgentId;
  round: number;
  factor: 'F2' | 'F3' | 'F4' | 'F5';
  title: string;
  value: string;
  source: string;
  /** Insurer weight for this claim type. */
  weight: number;
  /** How much the finding moves the verdict (0..1). */
  strength: number;
  /** How far the source can be trusted (0..1). */
  quality: number;
  direction: 1 | -1 | 0;
  /** Timeline offset at which the finding becomes known. */
  at: number;
}

export interface JudgeDecision {
  round: number;
  at: number;
  dur: number;
  hypotheses: { text: string; status: 'confirmed' | 'refuted' | 'open' | 'conflict' }[];
  tension?: string;
  redispatch?: { agent: AgentId; question: string }[];
  stop?: string;
  summary: string;
}

export interface Photo {
  id: string;
  name: string;
  hue: number;
  states: { at: number; status: Status; note: string; taken: string }[];
}

export interface Plan {
  hypotheses: { text: string; critical: boolean }[];
  dispatch: { agent: AgentId; question?: string; skipped?: string }[];
  note: string;
}

export interface MapSpec {
  kind: 'flood' | 'wind';
  zoneLabel: string;
  zoneAt: number;
  distanceLabel?: string;
  elevationLabel?: string;
  elevationAt?: number;
  stations?: { x: number; y: number; label: string }[];
}

export interface CaseFile {
  id: string;
  claimant: string;
  initials: string;
  type: ClaimType;
  typeLabel: string;
  place: string;
  address: string;
  event: string;
  eventDate: string;
  filed: string;
  lag: string;
  policy: string;
  claimed: string;
  description: string;
  profile: string;
  /** Base rate for this claim type before any evidence. */
  p0: number;
  duration: number;
  windows: StageWindow[];
  flags: StageId[];
  details: Partial<Record<StageId, DetailItem[]>>;
  plan: Plan;
  runs: AgentRun[];
  evidence: Evidence[];
  judge: JudgeDecision[];
  photos: Photo[];
  map: MapSpec;
  /** A hard authenticity gate that trips at `at` and overrides the score-based route. */
  gate?: { at: number; label: string; evidence: string };
  rationale: string;
}

export interface QueueCase {
  id: string;
  claimant: string;
  type: ClaimType;
  typeLabel: string;
  place: string;
  filed: string;
  description: string;
  status: 'new' | 'verdict';
  score?: number;
  route?: Route;
  signals?: string[];
}

/** Flat trace event: the shape the backend is expected to emit (see the workflow doc). */
export interface TraceEvent {
  case_id: string;
  step_id: string;
  parent?: string;
  actor: string;
  type: 'stage' | 'tool_call' | 'observation' | 'decision' | 'escalation';
  summary: string;
  outputs?: Record<string, string | number>;
  sources?: string[];
  status: 'done' | 'failed';
  started_at: number;
  ended_at: number;
}
