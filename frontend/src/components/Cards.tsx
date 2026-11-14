import { CalendarDays, FileText, MapPin, ShieldCheck, Wallet } from 'lucide-react';
import { useEased } from '../lib/hooks';
import { bandOf } from '../lib/score';
import { BANDS } from '../mock/meta';
import type { Band, CaseFile } from '../mock/types';

const BAND_ORDER: { id: Band; from: number; to: number }[] = [
  { id: 'unlikely', from: 0, to: 35 },
  { id: 'uncertain', from: 35, to: 65 },
  { id: 'likely', from: 65, to: 85 },
  { id: 'very-likely', from: 85, to: 100 },
];

export function ScoreMeter({ score, compact = false }: { score: number; compact?: boolean }) {
  const eased = useEased(score);
  const band = bandOf(score);
  return (
    <div className={`meter b-${band}${compact ? ' is-compact' : ''}`}>
      <div className="meter-track" role="img" aria-label={`Plausibility score ${score} out of 100, ${BANDS[band].label}`}>
        {BAND_ORDER.map((b) => (
          <span key={b.id} className={`meter-seg b-${b.id}${b.id === band ? ' is-on' : ''}`} style={{ flexGrow: b.to - b.from }} />
        ))}
        <span className="meter-pin" style={{ left: `${eased}%` }} />
      </div>
      <div className="meter-scale" aria-hidden="true">
        {BAND_ORDER.map((b) => (
          <span key={b.id} className={b.id === band ? 'is-on' : ''} style={{ flexGrow: b.to - b.from }}>
            {BANDS[b.id].label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ScoreCard({
  score,
  evidenceCount,
  phase,
  coverage,
  authenticity,
}: {
  score: number;
  evidenceCount: number;
  phase: 'idle' | 'base' | 'provisional' | 'final';
  coverage: 'pending' | 'passed';
  authenticity: 'pending' | 'passed' | 'flagged';
}) {
  const eased = useEased(score);
  const band = bandOf(score);
  return (
    <section className={`card score-card b-${band} phase-${phase}`}>
      <header className="card-head">
        <h3>Plausibility score</h3>
        <span className="chip">
          {phase === 'idle' ? 'Not started' : phase === 'base' ? 'Base rate' : phase === 'provisional' ? 'Provisional' : 'Final'}
        </span>
      </header>
      <div className="score-row">
        <span className="score-num">{phase === 'idle' ? '–' : Math.round(eased)}</span>
        <div>
          <p className="score-band">{phase === 'idle' ? 'Waiting for evidence' : BANDS[band].label}</p>
          <p className="score-sub">
            {phase === 'idle'
              ? 'Starts from the base rate for this claim type'
              : evidenceCount === 0
                ? 'Base rate, no findings yet'
                : `${evidenceCount} finding${evidenceCount === 1 ? '' : 's'} weighed`}
          </p>
        </div>
      </div>
      {phase !== 'idle' && <ScoreMeter score={score} />}
      <ul className="gates">
        <li className={`g-${coverage}`}>
          <span className="gate-dot" />
          Coverage gate
          <b>{coverage === 'passed' ? 'Passed' : 'Pending'}</b>
        </li>
        <li className={`g-${authenticity}`}>
          <span className="gate-dot" />
          Authenticity gate
          <b>{authenticity === 'passed' ? 'Passed' : authenticity === 'flagged' ? 'Flagged' : 'Pending'}</b>
        </li>
      </ul>
    </section>
  );
}

export function ClaimCard({ c }: { c: CaseFile }) {
  const rows = [
    { icon: MapPin, label: 'Loss address', value: c.address },
    { icon: CalendarDays, label: 'Event', value: `${c.event}, ${c.eventDate}` },
    { icon: FileText, label: 'Filed', value: `${c.filed} · ${c.lag.replace('Filed ', '')}` },
    { icon: ShieldCheck, label: 'Policy', value: c.policy },
    { icon: Wallet, label: 'Claimed', value: c.claimed },
  ];
  return (
    <section className="card claim-card">
      <header className="card-head">
        <h3>The claim</h3>
        <span className="chip">{c.profile}</span>
      </header>
      <p className="claim-desc">“{c.description}”</p>
      <dl className="facts">
        {rows.map((r) => (
          <div key={r.label}>
            <dt>
              <r.icon size={14} />
              {r.label}
            </dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function MapCard({ c, t }: { c: CaseFile; t: number }) {
  const m = c.map;
  const zone = t >= m.zoneAt;
  const elev = m.elevationAt !== undefined && t >= m.elevationAt;
  const flood = m.kind === 'flood';
  const house = flood ? { x: 236, y: 178 } : { x: 206, y: 128 };
  return (
    <section className="card map-card">
      <header className="card-head">
        <h3>Where it happened</h3>
        <span className="chip">{c.place}</span>
      </header>
      <div className={`map kind-${m.kind}${zone ? ' has-zone' : ''}`}>
        <svg viewBox="0 0 360 230" role="img" aria-label={flood ? `Map: the house is ${m.distanceLabel ?? ''} outside the mapped flood extent` : 'Map: the house is inside the strong-gust area'}>
          <rect width="360" height="230" className="map-land" />
          <g className="map-roads">
            <path d="M-10 150 C80 140 160 172 370 150" />
            <path d="M120 -10 C132 70 108 150 130 240" />
            <path d="M250 -10 C240 80 262 160 244 240" />
            <path d="M-10 205 C100 196 220 214 370 200" />
          </g>
          {flood ? (
            <>
              <path className="map-zone" d="M-5 22 C70 6 122 52 180 42 S300 6 365 30 L365 112 C300 96 252 128 192 120 S82 140 -5 108 Z" />
              <path className="map-river" d="M-10 62 C60 42 110 96 170 80 S290 42 370 70" />
            </>
          ) : (
            <path className="map-zone" d="M-5 40 C80 -6 240 18 365 96 L365 232 L150 232 C90 170 20 150 -5 120 Z" />
          )}
          {zone && flood && (
            <g className="map-measure">
              <line x1={house.x} y1={house.y - 10} x2={house.x} y2={124} />
              <rect x={house.x + 8} y={139} width="52" height="20" rx="10" />
              <text x={house.x + 34} y={153} textAnchor="middle">
                {m.distanceLabel}
              </text>
            </g>
          )}
          {zone &&
            m.stations?.map((s) => (
              <g key={s.label} className="map-station">
                <circle cx={s.x} cy={s.y} r="13" />
                <text x={s.x} y={s.y + 4} textAnchor="middle">
                  {s.label}
                </text>
              </g>
            ))}
          <g className="map-house" transform={`translate(${house.x} ${house.y})`}>
            <circle r="16" className="map-house-halo" />
            <circle r="7" className="map-house-dot" />
          </g>
          {elev && (
            <g className="map-elev" transform={`translate(${house.x - 96} ${house.y + 12})`}>
              <rect width="86" height="24" rx="12" />
              <text x="43" y="16" textAnchor="middle">
                {m.elevationLabel} higher
              </text>
            </g>
          )}
        </svg>
      </div>
      <ul className="map-legend">
        <li>
          <span className="lg lg-house" />
          Insured house
        </li>
        <li className={zone ? '' : 'is-off'}>
          <span className="lg lg-zone" />
          {zone ? m.zoneLabel : 'Event footprint not loaded yet'}
        </li>
      </ul>
    </section>
  );
}
