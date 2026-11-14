/**
 * Two groups of types.
 *
 * 1. "Api*" types: exactly what the ClaimLens backend returns (backend/app/main.py). Names are the backend's.
 * 2. View types (CaseFile, AgentRun, ...): what the screens draw. src/api/build.ts turns group 1 into group 2.
 *
 * Identifiers shared by both groups (agents, bands, outcomes, damage types, verdicts) use the backend's spelling.
 */

// ---------------------------------------------------------------- shared identifiers (backend spelling)

export type AgentId = 'meteo' | 'satellite' | 'risk_zones' | 'photo_forensics' | 'street_view' | 'news';
export type Verdict = 'supports' | 'contradicts' | 'inconclusive';
export type Band = 'very_likely' | 'likely' | 'uncertain' | 'unlikely';
export type Outcome = 'fast_track' | 'standard_review' | 'antifraud_referral';
export type ClaimType = 'flood' | 'storm';
export type ClaimStatus = 'received' | 'investigating' | 'paused' | 'awaiting_decision' | 'decided';
export type Mark = 'confirmed' | 'refuted' | 'inconclusive' | 'conflicting';

// ---------------------------------------------------------------- backend responses

/** One row of GET /claims. */
export interface ApiClaimRow {
  id: string;
  address: string;
  damage_type: ClaimType;
  event_date: string;
  status: ClaimStatus;
  score: number | null;
  band: Band | null;
  recommendation: Outcome | null;
  decision: 'approve' | 'modify' | null;
  outcome: Outcome | null;
  created_at: string;
}

export interface ApiClaim {
  id: string;
  policy_id: string;
  damage_type: ClaimType;
  event_date: string;
  notified_at: string | null;
  address: string;
  lat: number | null;
  lon: number | null;
  description: string | null;
  amount_claimed: number | null;
  photos: string[] | null;
  status: ClaimStatus;
  decision: 'approve' | 'modify' | null;
  outcome: Outcome | null;
  decision_reason: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface ApiPolicy {
  id: string;
  holder_name: string;
  address: string;
  valid_from: string;
  valid_to: string;
  covered_risks: string[];
  sum_insured: number;
  product: string;
}

export interface ApiRuleFlag {
  rule: string;
  passed: boolean;
  reason: string;
}

export interface ApiHypothesis {
  id: string;
  text: string;
  critical: boolean;
  agents: string[];
}

export interface ApiFinding {
  metric: string;
  value: unknown;
  unit: string | null;
  source: string;
  url: string | null;
}

export interface ApiEvidence {
  id: number;
  rejected_by_adjuster: boolean;
  agent: AgentId;
  round: number;
  hypothesis: string;
  verdict: Verdict;
  strength: number;
  data_quality: number;
  findings: ApiFinding[];
  reasoning_steps: string[];
  gaps: string[];
}

export interface ApiContribution {
  /** An agent id, or "context" for the policy-context term. */
  agent: string;
  round: number;
  delta_logit: number;
  /** Shown as is for a `client` line; null for the others. */
  reason?: string | null;
}

export interface ApiGate {
  kind: 'coverage' | 'clear_fake';
  reason: string;
}

export interface ApiScore {
  score: number;
  band: Band;
  recommendation: Outcome;
  contributions: ApiContribution[];
  gates: ApiGate[];
}

export type CheckStep = 'intake' | 'documents' | 'client' | 'policy' | 'photos';

export interface ApiCheckItem {
  id: string;
  label: string;
  value: string | null;
  status: 'ok' | 'flag' | 'fail' | 'info';
  reason: string | null;
}

export interface ApiFlag {
  step: CheckStep;
  code: string;
  field: string | null;
  severity: 'warn' | 'fail';
  reason: string;
}

export interface ApiStepResult {
  step: CheckStep;
  items: ApiCheckItem[];
  flags: ApiFlag[];
}

/** Fields read from the two PDFs, by form-field name (not fixed: the backend owns them). */
export interface ApiDocuments {
  claim_form?: Record<string, string>;
  policy?: Record<string, string>;
}

/** GET /claims/{id}. */
export interface ApiClaimDetail {
  claim: ApiClaim;
  policy: ApiPolicy | null;
  rule_flags: ApiRuleFlag[];
  hypotheses: ApiHypothesis[];
  not_relevant_agents: AgentId[];
  evidence: ApiEvidence[];
  score: ApiScore | null;
  score_history: { round: number; score: number; band: Band }[];
  /** Empty for a claim not yet run or stored without documents. */
  checks: Partial<Record<CheckStep, ApiStepResult>>;
  flags: ApiFlag[];
  documents: ApiDocuments;
  run_mode: 'live' | 'replay' | 'record' | null;
}

/** One item of GET /claims/{id}/trace, and one `trace` event on the live stream. */
export interface ApiTraceStep {
  case_id: string;
  step_id: string;
  parent: string | null;
  actor: string;
  type: 'tool_call' | 'observation' | 'decision' | 'escalation';
  summary: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  sources: string[];
  status: string;
  started_at: string;
  ended_at: string | null;
}

// ---------------------------------------------------------------- view model

export type StageId = 'intake' | 'documents' | 'client' | 'policy' | 'photos' | 'plan' | 'agents' | 'judge' | 'verdict' | 'review';
export type Status = 'ok' | 'flag' | 'fail' | 'info';

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
  label: string;
  value?: string;
  status?: Status;
  note?: string;
}

/** One line of an agent's trail: a source it queried, or something it worked out. */
export interface ToolCall {
  id: string;
  at: number;
  dur: number;
  /** Source that was queried; empty for a line the agent worked out itself. */
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
  gaps: string[];
}

export interface Evidence {
  /** Backend evidence id (used by "set aside"). */
  id: number;
  agent: AgentId;
  round: number;
  title: string;
  detail: string;
  source: string;
  verdict: Verdict;
  rejected: boolean;
  /** Timeline offset at which the finding becomes known. */
  at: number;
}

/** The score as the backend computed it at one moment of the run. */
export interface ScoreStep extends ApiScore {
  round: number;
  at: number;
}

export interface JudgeDecision {
  round: number;
  at: number;
  dur: number;
  hypotheses: { id: string; text: string; mark: Mark }[];
  tensions: string[];
  redispatch?: { agent: AgentId; question: string }[];
  stop?: string;
  summary: string;
}

export interface Photo {
  name: string;
  url: string;
  status: Status;
  notes: string[];
  /** Timeline offset at which the photo checks are known. */
  at: number;
}

export interface Plan {
  hypotheses: { id: string; text: string; critical: boolean }[];
  dispatch: { agent: AgentId; question?: string; skipped?: boolean }[];
}

export interface LatLon {
  lat: number;
  lon: number;
}

/** Real map data for a flood claim. Absent when the backend has no mapped flood for the claim. */
export interface MapSpec {
  house: LatLon;
  activation: string;
  mapDate?: string;
  inside: boolean;
  distanceM?: number;
  edge?: LatLon;
  zoneAt: number;
  water?: LatLon & { name?: string; distanceM?: number };
  elevationDiffM?: number;
  elevationAt?: number;
}

export interface Decision {
  kind: 'approve' | 'modify';
  outcome: Outcome;
  reason?: string;
  at: string;
}

export interface Question {
  text: string;
  agent?: AgentId;
  round: number;
  at: number;
}

export interface CaseFile {
  id: string;
  status: ClaimStatus;
  claimant: string;
  type: ClaimType;
  typeLabel: string;
  place: string;
  address: string;
  eventDate: string;
  filed: string;
  lag: string;
  policy: string;
  claimed: string;
  description: string;
  /** End of the recorded run in ms. Very large while a run is still going. */
  duration: number;
  /** Latest moment known so far, in ms. Equals `duration` once the run is over. */
  edge: number;
  /** True when the run was too fast to watch (served from saved responses) and the replay uses even pacing. */
  paced: boolean;
  windows: StageWindow[];
  /** Stages with something flagged: drawn with a flag on the rail. */
  flaggedStages: StageId[];
  /** Every flag of the five early steps. */
  flags: ApiFlag[];
  documents: ApiDocuments;
  runMode: 'live' | 'replay' | 'record' | null;
  /** Set while the run waits after a failed policy rule. */
  paused?: { rules: string[] };
  details: Partial<Record<StageId, DetailItem[]>>;
  plan: Plan;
  runs: AgentRun[];
  evidence: Evidence[];
  scores: ScoreStep[];
  judge: JudgeDecision[];
  photos: Photo[];
  map?: MapSpec;
  rulesPassed: boolean;
  rationale: string;
  decision?: Decision;
  questions: Question[];
  /** Set when the investigation stopped with an error. */
  error?: string;
}

export interface QueueCase {
  id: string;
  claimant: string;
  type: ClaimType;
  typeLabel: string;
  place: string;
  filed: string;
  description: string;
  status: ClaimStatus;
  score?: number;
  band?: Band;
  /** The adjuster's outcome once decided, otherwise the recommendation. */
  outcome?: Outcome;
  decided: boolean;
  signals: string[];
  /** Archived demo history: shown in the queue, never opened or sent to the backend. */
  mock?: boolean;
}
