import type { AgentId, Band, Route, StageId } from './types';

export const APP_NAME = 'AsigIT';

export const STAGES: { id: StageId; short: string; live: string; title: string; help: string }[] = [
  { id: 'intake', short: 'Intake', live: 'Receiving the claim', title: 'Intake', help: 'The claim form, the policy and the photos arrive and get a case number.' },
  { id: 'client', short: 'Client data', live: 'Validating client data', title: 'Client data validation', help: 'Checks that the person, the address and the contact details are complete and match the policy.' },
  { id: 'documents', short: 'Documents', live: 'Parsing client documents', title: 'Document parsing', help: 'Reads the form and the policy and pulls out the fields. Anything read with low confidence is yours to correct.' },
  { id: 'policy', short: 'Policy check', live: 'Validating claim conditions', title: 'Claim conditions', help: 'Fixed rules, no AI: was the policy active, is the peril covered, was the claim filed in time.' },
  { id: 'photos', short: 'Photo check', live: 'Checking photo metadata', title: 'Photo pre-screen', help: 'A quick metadata check on every photo before any agent spends time on the claim.' },
  { id: 'plan', short: 'Plan', live: 'Building the orchestrator plan', title: 'Orchestrator plan', help: 'The orchestrator turns the claim into things to prove and picks which agents to ask.' },
  { id: 'agents', short: 'Agents', live: "Pulling data from the orchestrator's agents", title: 'Specialist agents', help: 'Each agent answers one question from one kind of source, then reports back.' },
  { id: 'judge', short: 'Judge', live: 'Judge is weighing the evidence', title: 'Judge', help: 'The judge weighs the findings, looks for contradictions and decides whether to send agents back.' },
  { id: 'verdict', short: 'Verdict', live: 'Building the case file', title: 'Verdict', help: 'Everything is assembled into a score, a recommended route and a file of sources.' },
  { id: 'review', short: 'Review', live: 'Waiting for your decision', title: 'Your decision', help: 'The system only recommends. Nothing is paid or refused until you decide.' },
];

export const ORDER: StageId[] = STAGES.map((s) => s.id);

export const AGENTS: { id: AgentId; name: string; source: string }[] = [
  { id: 'weather', name: 'Weather', source: 'Open-Meteo · ERA5-Land' },
  { id: 'satellite', name: 'Satellite', source: 'Copernicus GFM · Sentinel-1' },
  { id: 'streetview', name: 'Street view', source: 'Street-level imagery' },
  { id: 'news', name: 'Local news', source: 'News search · ISU bulletins' },
  { id: 'risk', name: 'Risk zones', source: 'OpenStreetMap · Copernicus DEM' },
  { id: 'forensics', name: 'Photo forensics', source: 'EXIF · image hashing' },
];

export const agentName = (id: AgentId) => AGENTS.find((a) => a.id === id)!.name;

export const BANDS: Record<Band, { label: string; range: string }> = {
  'very-likely': { label: 'Very likely', range: '85–100' },
  likely: { label: 'Likely', range: '65–84' },
  uncertain: { label: 'Uncertain', range: '35–64' },
  unlikely: { label: 'Unlikely', range: '0–34' },
};

export const ROUTES: Record<Route, { label: string; action: string; desc: string }> = {
  'fast-track': {
    label: 'Fast-track',
    action: 'Fast-track payment',
    desc: 'Evidence is strong and consistent. Pay without a site visit.',
  },
  standard: {
    label: 'Standard review',
    action: 'Send to standard review',
    desc: 'Plausible, with open points. An adjuster visits the site.',
  },
  investigate: {
    label: 'Investigate',
    action: 'Refer to special investigations',
    desc: 'Evidence contradicts the claim. Hand over with the full file.',
  },
};
