import type { AgentId, Band, ClaimType, Mark, Outcome, StageId } from './types';

export const APP_NAME = 'ClaimIT';

/** "1 agent", "3 agenți", "20 de agenți": Romanian counts take "de" from 20 up. */
export const nr = (n: number, one: string, many: string) => (n === 1 ? `1 ${one}` : `${n} ${n % 100 >= 20 || (n >= 100 && n % 100 === 0) ? 'de ' : ''}${many}`);

/** The checkpoints on the rail. Each one is something the backend really does (see docs/frontend-integration.md). */
export const STAGES: { id: StageId; short: string; live: string; title: string; help: string }[] = [
  { id: 'intake', short: 'Dosar', live: 'Se citește dosarul', title: 'Dosarul depus', help: 'Datele din dosar: asiguratul, adresa, data evenimentului, suma și polița.' },
  { id: 'documents', short: 'Documente', live: 'Se citesc formularul de daună și polița', title: 'Cele două documente', help: 'Formularul de daună și polița în PDF sunt citite automat, fără AI, și comparate cu datele din dosar.' },
  { id: 'client', short: 'Date client', live: 'Se verifică datele clientului', title: 'Datele clientului', help: 'Verificări automate pe datele asiguratului din formular: CNP, telefon, e-mail, cont bancar și adresa pe hartă.' },
  { id: 'policy', short: 'Poliță', live: 'Se verifică polița', title: 'Condițiile poliței', help: 'Verificări automate, fără AI: dacă polița era activă, dacă riscul este acoperit și dacă dauna a fost avizată la timp.' },
  { id: 'photos', short: 'Fotografii', live: 'Se verifică fotografiile', title: 'Verificarea fotografiilor', help: 'Există fotografii, se pot citi și au dată și loc? Verificări automate, fără AI.' },
  { id: 'plan', short: 'Plan', live: 'Se stabilește ce trebuie verificat', title: 'Planul de verificare', help: 'Sistemul stabilește ce trebuie dovedit și alege agenții care verifică fiecare lucru.' },
  { id: 'agents', short: 'Agenți', live: 'Agenții caută informații', title: 'Agenții specializați', help: 'Fiecare agent verifică un singur lucru, folosind un singur tip de sursă.' },
  { id: 'judge', short: 'Arbitru', live: 'Arbitrul analizează dovezile', title: 'Arbitrul', help: 'Arbitrul compară rezultatele, caută contradicții și decide dacă mai este nevoie de verificări.' },
  { id: 'verdict', short: 'Verdict', live: 'Se întocmește raportul', title: 'Verdictul', help: 'Rezultatele se adună într-un scor, o recomandare și lista surselor folosite.' },
  { id: 'review', short: 'Decizie', live: 'Decizia vă aparține', title: 'Decizia dumneavoastră', help: 'Sistemul doar recomandă. Nimic nu se plătește și nu se respinge fără decizia dumneavoastră.' },
];

export const ORDER: StageId[] = STAGES.map((s) => s.id);

/** The six backend agents, in the order the backend lists them. Ids are the backend's. */
export const AGENTS: { id: AgentId; name: string; source: string }[] = [
  { id: 'meteo', name: 'Meteo', source: 'Reanaliză Open-Meteo' },
  { id: 'satellite', name: 'Satelit', source: 'Hărți de inundație Copernicus CEMS' },
  { id: 'risk_zones', name: 'Zone de risc', source: 'OpenStreetMap · Copernicus DEM' },
  { id: 'photo_forensics', name: 'Analiză foto', source: 'EXIF · amprentă imagine · căutare web' },
  { id: 'street_view', name: 'Imagini stradale', source: 'Mapillary · Google Street View' },
  { id: 'news', name: 'Presă locală', source: 'GDELT · căutare știri' },
];

export const isAgent = (id: string): id is AgentId => AGENTS.some((a) => a.id === id);
export const agentName = (id: string) => AGENTS.find((a) => a.id === id)?.name ?? (id === 'context' ? 'Contextul poliței' : id);

export const BANDS: Record<Band, { label: string; range: string }> = {
  very_likely: { label: 'Foarte plauzibil', range: '85–100' },
  likely: { label: 'Plauzibil', range: '65–84' },
  uncertain: { label: 'Incert', range: '35–64' },
  unlikely: { label: 'Puțin plauzibil', range: '0–34' },
};

/** The three outcomes the backend knows. The AI only recommends one; the adjuster decides. */
export const OUTCOMES: Record<Outcome, { label: string; action: string; desc: string }> = {
  fast_track: {
    label: 'Plată rapidă',
    action: 'Plată rapidă',
    desc: 'Dovezile sunt solide și concordante. Se plătește fără inspecție.',
  },
  standard_review: {
    label: 'Analiză standard',
    action: 'Analiză standard',
    desc: 'Dauna este plauzibilă, dar rămân puncte deschise. Un inspector merge la fața locului.',
  },
  antifraud_referral: {
    label: 'Antifraudă',
    action: 'Trimitere la antifraudă',
    desc: 'Dovezile contrazic dauna. Dosarul complet merge la echipa antifraudă.',
  },
};

export const TYPE_LABEL: Record<ClaimType, string> = { flood: 'Inundație', storm: 'Furtună' };

export const MARK_TEXT: Record<Mark, string> = {
  confirmed: 'Confirmată',
  refuted: 'Infirmată',
  inconclusive: 'Neconcludentă',
  conflicting: 'Contradictorie',
};

/** Labels for the backend's policy rules (backend/engine/rules.py). The reason text comes from the backend. */
export const RULE_LABEL: Record<string, string> = {
  policy_active: 'Polița era activă la data evenimentului',
  waiting_period: 'Perioada de așteptare s-a încheiat',
  risk_covered: 'Riscul este acoperit de poliță',
  address_match: 'Adresa daunei este adresa asigurată',
  notified_in_time: 'Avizare în termen',
};
