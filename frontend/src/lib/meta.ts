import type { AgentId, Band, ClaimType, Mark, Outcome, StageId } from './types';

export const APP_NAME = 'AsigIT';

/** The checkpoints on the rail. Each one is something the backend really does (see docs/frontend-integration.md). */
export const STAGES: { id: StageId; short: string; live: string; title: string; help: string }[] = [
  { id: 'intake', short: 'Claim', live: 'Reading the claim', title: 'The claim on file', help: 'What the backend holds for this claim: who, where, when, how much and which policy.' },
  { id: 'documents', short: 'Documents', live: 'Reading the claim form and the policy', title: 'The two documents', help: 'The claim form and the policy PDF are read back by code, never an AI, and compared with what was filed.' },
  { id: 'client', short: 'Client data', live: 'Checking the client data', title: 'Client data', help: 'Fixed checks on what the form says about the policyholder: ID number, phone, email, bank account and the address on the map.' },
  { id: 'policy', short: 'Policy check', live: 'Validating claim conditions', title: 'Claim conditions', help: 'Fixed rules, no AI: was the policy active, is the peril covered, was the claim filed in time.' },
  { id: 'photos', short: 'Photos', live: 'Checking the photos', title: 'Photo check', help: 'Are there photos, can they be read, and do they carry a date and place. Fixed checks, no AI.' },
  { id: 'plan', short: 'Plan', live: 'Building the orchestrator plan', title: 'Orchestrator plan', help: 'The orchestrator turns the claim into things to prove and picks which agents to ask.' },
  { id: 'agents', short: 'Agents', live: "Pulling data from the orchestrator's agents", title: 'Specialist agents', help: 'Each agent answers one question from one kind of source, then reports back.' },
  { id: 'judge', short: 'Judge', live: 'Judge is weighing the evidence', title: 'Judge', help: 'The judge weighs the findings, looks for contradictions and decides whether to send agents back.' },
  { id: 'verdict', short: 'Verdict', live: 'Building the case file', title: 'Verdict', help: 'Everything is assembled into a score, a recommended route and a file of sources.' },
  { id: 'review', short: 'Review', live: 'Waiting for your decision', title: 'Your decision', help: 'The system only recommends. Nothing is paid or refused until you decide.' },
];

export const ORDER: StageId[] = STAGES.map((s) => s.id);

/** The six backend agents, in the order the backend lists them. Ids are the backend's. */
export const AGENTS: { id: AgentId; name: string; source: string }[] = [
  { id: 'meteo', name: 'Weather', source: 'Open-Meteo reanalysis' },
  { id: 'satellite', name: 'Satellite', source: 'Copernicus CEMS flood maps' },
  { id: 'risk_zones', name: 'Risk zones', source: 'OpenStreetMap · Copernicus DEM' },
  { id: 'photo_forensics', name: 'Photo forensics', source: 'EXIF · image hashing · web search' },
  { id: 'street_view', name: 'Street view', source: 'Mapillary · Google Street View' },
  { id: 'news', name: 'Local news', source: 'GDELT · news search' },
];

export const isAgent = (id: string): id is AgentId => AGENTS.some((a) => a.id === id);
export const agentName = (id: string) => AGENTS.find((a) => a.id === id)?.name ?? (id === 'context' ? 'Policy context' : id);

export const BANDS: Record<Band, { label: string; range: string }> = {
  very_likely: { label: 'Very likely', range: '85–100' },
  likely: { label: 'Likely', range: '65–84' },
  uncertain: { label: 'Uncertain', range: '35–64' },
  unlikely: { label: 'Unlikely', range: '0–34' },
};

/** The three outcomes the backend knows. The AI only recommends one; the adjuster decides. */
export const OUTCOMES: Record<Outcome, { label: string; action: string; desc: string }> = {
  fast_track: {
    label: 'Fast-track',
    action: 'Fast-track payment',
    desc: 'Evidence is strong and consistent. Pay without a site visit.',
  },
  standard_review: {
    label: 'Standard review',
    action: 'Send to standard review',
    desc: 'Plausible, with open points. An adjuster visits the site.',
  },
  antifraud_referral: {
    label: 'Antifraud referral',
    action: 'Refer to the antifraud team',
    desc: 'Evidence contradicts the claim. Hand over with the full file.',
  },
};

export const TYPE_LABEL: Record<ClaimType, string> = { flood: 'Flood', storm: 'Storm' };

export const MARK_TEXT: Record<Mark, string> = {
  confirmed: 'Confirmed',
  refuted: 'Refuted',
  inconclusive: 'Inconclusive',
  conflicting: 'In conflict',
};

/** English labels for the backend's policy rules (backend/engine/rules.py). The reason text comes from the backend. */
export const RULE_LABEL: Record<string, string> = {
  policy_active: 'Policy active on the event date',
  waiting_period: 'Waiting period over',
  risk_covered: 'Peril covered by the policy',
  address_match: 'Loss address matches the insured address',
  notified_in_time: 'Notified in time',
};
