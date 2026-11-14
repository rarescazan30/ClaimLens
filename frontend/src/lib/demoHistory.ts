import type { QueueCase } from './types';

const base = { status: 'decided' as const, decided: true, mock: true, description: '' };

/** Three already-processed claims, shown only in the queue's verdict section. Never fetched, never run. */
export const DEMO_HISTORY: QueueCase[] = [
  { ...base, id: 'C-7001', claimant: 'Elena Dumitru', type: 'flood', typeLabel: 'Inundație', place: 'Tecuci, jud. Galați', filed: '18 sept. 2024', score: 88.4, band: 'very_likely', outcome: 'fast_track',
    signals: ['Ploaie de 52 mm în 24 de ore', 'Casa se află în zona inundată Copernicus', '4 relatări de presă despre inundație'] },
  { ...base, id: 'C-7002', claimant: 'Gheorghe Matei', type: 'storm', typeLabel: 'Furtună', place: 'Galați', filed: '28 nov. 2023', score: 71.2, band: 'likely', outcome: 'standard_review',
    signals: ['Rafale de vânt de 92 km/h în zi', 'Alertă meteo cod portocaliu pentru județ', 'Fotografiile arată acoperișul avariat'] },
  { ...base, id: 'C-7003', claimant: 'Ana Constantin', type: 'flood', typeLabel: 'Inundație', place: 'Pechea, jud. Galați', filed: '20 sept. 2024', score: 22.6, band: 'unlikely', outcome: 'antifraud_referral',
    signals: ['Fotografie publicată online înainte de eveniment', 'Casa se află la 12 m deasupra zonei inundate', 'Nicio relatare locală despre inundație'] },
];

export const withHistory = (rows: QueueCase[]): QueueCase[] => [...rows, ...DEMO_HISTORY.filter((h) => !rows.some((r) => r.id === h.id))];

/** The queue's "Dosare cu verdict" group, best score first. */
export const verdictRows = (rows: QueueCase[]) =>
  rows.filter((r) => r.status === 'awaiting_decision' || r.status === 'decided').sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

export const isOpenable = (r: QueueCase) => !r.mock;
