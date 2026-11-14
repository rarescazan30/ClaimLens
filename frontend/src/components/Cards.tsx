import { CalendarDays, FileText, MapPin, ShieldCheck, Wallet } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { getFloodExtent, type GeoJSON } from '../api/client';
import { useEased } from '../lib/hooks';
import { BANDS } from '../lib/meta';
import { fmtScore } from '../lib/score';
import type { Band, CaseFile, LatLon } from '../lib/types';
import { Empty } from './ui';

const BAND_ORDER: { id: Band; from: number; to: number }[] = [
  { id: 'unlikely', from: 0, to: 35 },
  { id: 'uncertain', from: 35, to: 65 },
  { id: 'likely', from: 65, to: 85 },
  { id: 'very_likely', from: 85, to: 100 },
];

/** A score that glides to its value, then rests on the backend's exact number. */
export function ScoreNumber({ score, ms }: { score: number; ms?: number }) {
  const eased = useEased(score, ms);
  return <>{Math.abs(eased - score) < 0.05 ? fmtScore(score) : Math.round(eased)}</>;
}

export function ScoreMeter({ score, band, compact = false }: { score: number; band: Band; compact?: boolean }) {
  const eased = useEased(score);
  return (
    <div className={`meter b-${band}${compact ? ' is-compact' : ''}`}>
      <div className="meter-track" role="img" aria-label={`Plausibility score ${fmtScore(score)} out of 100, ${BANDS[band].label}`}>
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

export type GateState = 'pending' | 'passed' | 'flagged' | 'none';
const GATE_TEXT: Record<GateState, string> = { pending: 'Pending', passed: 'Passed', flagged: 'Flagged', none: 'No photos to check' };

export function ScoreCard({
  score,
  band,
  evidenceCount,
  phase,
  coverage,
  authenticity,
}: {
  score?: number;
  band?: Band;
  evidenceCount: number;
  phase: 'idle' | 'base' | 'provisional' | 'final';
  coverage: GateState;
  authenticity: GateState;
}) {
  const has = score !== undefined && band !== undefined;
  return (
    <section className={`card score-card b-${band ?? 'uncertain'} phase-${has ? phase : 'idle'}`}>
      <header className="card-head">
        <h3>Plausibility score</h3>
        <span className="chip">{phase === 'idle' ? 'Not started' : phase === 'base' ? 'Waiting for evidence' : phase === 'provisional' ? 'Provisional' : 'Final'}</span>
      </header>
      <div className="score-row">
        <span className="score-num">{has ? <ScoreNumber score={score} /> : '–'}</span>
        <div>
          <p className="score-band">{has ? BANDS[band].label : 'Waiting for evidence'}</p>
          <p className="score-sub">
            {has ? `${evidenceCount} finding${evidenceCount === 1 ? '' : 's'} weighed` : 'The score appears after the first round of agents'}
          </p>
        </div>
      </div>
      {has && <ScoreMeter score={score} band={band} />}
      <ul className="gates">
        <li className={`g-${coverage}`}>
          <span className="gate-dot" />
          Coverage gate
          <b>{GATE_TEXT[coverage]}</b>
        </li>
        <li className={`g-${authenticity === 'none' ? 'pending' : authenticity}`}>
          <span className="gate-dot" />
          Authenticity gate
          <b>{GATE_TEXT[authenticity]}</b>
        </li>
      </ul>
    </section>
  );
}

export function ClaimCard({ c }: { c: CaseFile }) {
  const rows = [
    { icon: MapPin, label: 'Loss address', value: c.address },
    { icon: CalendarDays, label: 'Event', value: `${c.typeLabel}, ${c.eventDate}` },
    { icon: FileText, label: 'Filed', value: `${c.filed} · ${c.lag.replace('Filed ', '')}` },
    { icon: ShieldCheck, label: 'Policy', value: c.policy },
    { icon: Wallet, label: 'Claimed', value: c.claimed },
  ];
  return (
    <section className="card claim-card">
      <header className="card-head">
        <h3>The claim</h3>
        <span className="chip">{c.id}</span>
      </header>
      {c.description && <p className="claim-desc">“{c.description}”</p>}
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

// ---------------------------------------------------------------- map

const VW = 360;
const VH = 230;
const floodCache = new Map<string, Promise<GeoJSON>>();

/** Metres east and south of the house, on flat ground (fine at this scale). */
const metres = (p: LatLon, house: LatLon) => ({
  x: (p.lon - house.lon) * 111_320 * Math.cos((house.lat * Math.PI) / 180),
  y: -(p.lat - house.lat) * 110_540,
});

const niceScale = (m: number) => [50, 100, 200, 500, 1000, 2000].find((s) => s >= m) ?? 5000;

/**
 * The house and the flood the backend mapped for this claim (Copernicus polygons from GET /claims/{id}/flood-extent),
 * drawn to scale. Shown only for claims that have a mapped flood.
 */
export function MapCard({ c, t }: { c: CaseFile; t: number }) {
  const m = c.map;
  const [geo, setGeo] = useState<GeoJSON | null | undefined>(undefined);
  useEffect(() => {
    if (!m) return;
    let on = true;
    let req = floodCache.get(c.id);
    if (!req) {
      req = getFloodExtent(c.id);
      floodCache.set(c.id, req);
      req.catch(() => floodCache.delete(c.id));
    }
    req.then((g) => on && setGeo(g)).catch(() => on && setGeo(null));
    return () => {
      on = false;
    };
  }, [c.id, m]);

  // Half the view height in metres: wide enough for the flood edge and, if close, the nearest water.
  const reach = m ? Math.max(m.distanceM ?? 0, Math.min(m.water?.distanceM ?? 0, 900)) : 0;
  const half = Math.min(2500, Math.max(300, reach * 1.7));
  const k = VH / 2 / half;
  const px = (p: LatLon) => {
    const q = metres(p, m!.house);
    return { x: VW / 2 + q.x * k, y: VH / 2 + q.y * k };
  };

  const zonePath = useMemo(() => {
    if (!geo || !m) return '';
    const parts: string[] = [];
    const ring = (r: number[][]) => {
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      const pts = r.map(([lon, lat]) => {
        const p = px({ lat, lon });
        minX = Math.min(minX, p.x);
        maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y);
        maxY = Math.max(maxY, p.y);
        return p;
      });
      if (maxX < 0 || minX > VW || maxY < 0 || minY > VH) return; // nowhere near the view
      parts.push(`M${pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join('L')}Z`);
    };
    for (const f of geo.features) {
      const g = f.geometry;
      if (!g) continue;
      if (g.type === 'Polygon') (g.coordinates as number[][][]).forEach(ring);
      else if (g.type === 'MultiPolygon') (g.coordinates as number[][][][]).forEach((poly) => poly.forEach(ring));
    }
    return parts.join('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo, half]);

  if (!m) return null;
  const zone = t >= m.zoneAt;
  const elev = m.elevationDiffM !== undefined && m.elevationAt !== undefined && t >= m.elevationAt;
  const house = { x: VW / 2, y: VH / 2 };
  const edge = m.edge ? px(m.edge) : undefined;
  const water = m.water ? px(m.water) : undefined;
  const waterVisible = water && water.x > 8 && water.x < VW - 8 && water.y > 8 && water.y < VH - 8;
  const bar = niceScale(half / 3);
  const distance = m.distanceM !== undefined ? `${Math.round(m.distanceM)} m` : '';
  const zoneLabel = `Flood mapped by Copernicus (${m.activation}${m.mapDate ? `, ${m.mapDate.slice(0, 10)}` : ''})`;

  return (
    <section className="card map-card">
      <header className="card-head">
        <h3>Where it happened</h3>
        <span className="chip">{c.place}</span>
      </header>
      {geo === null ? (
        <Empty title="The flood map could not be loaded" body="The backend did not return the mapped flood for this claim. The distances in the findings still stand." />
      ) : (
        <div className={`map kind-flood${zone && geo ? ' has-zone' : ''}`}>
          <svg
            viewBox={`0 0 ${VW} ${VH}`}
            role="img"
            aria-label={m.inside ? 'Map: the house is inside the mapped flood' : `Map: the house is ${distance} outside the mapped flood`}
          >
            <rect width={VW} height={VH} className="map-land" />
            <path className="map-zone" d={zonePath} fillRule="evenodd" />
            {zone && edge && !m.inside && (
              <g className="map-measure">
                <line x1={house.x} y1={house.y} x2={edge.x} y2={edge.y} />
                <rect x={(house.x + edge.x) / 2 + 8} y={(house.y + edge.y) / 2 - 10} width="52" height="20" rx="10" />
                <text x={(house.x + edge.x) / 2 + 34} y={(house.y + edge.y) / 2 + 4} textAnchor="middle">
                  {distance}
                </text>
              </g>
            )}
            {zone && waterVisible && (
              <g className="map-station">
                <circle cx={water.x} cy={water.y} r="4" />
                <text x={water.x + 8} y={water.y + 4}>
                  {m.water?.name ?? 'Nearest water'}
                </text>
              </g>
            )}
            <g className="map-house" transform={`translate(${house.x} ${house.y})`}>
              <circle r="16" className="map-house-halo" />
              <circle r="7" className="map-house-dot" />
            </g>
            {elev && (
              <g className="map-elev" transform={`translate(${house.x - 104} ${house.y + 14})`}>
                <rect width="94" height="24" rx="12" />
                <text x="47" y="16" textAnchor="middle">
                  {m.elevationDiffM! >= 0 ? `${m.elevationDiffM} m higher` : `${Math.abs(m.elevationDiffM!)} m lower`}
                </text>
              </g>
            )}
            <g className="map-scale">
              <line x1={12} y1={VH - 12} x2={12 + bar * k} y2={VH - 12} />
              <text x={12} y={VH - 17}>
                {bar >= 1000 ? `${bar / 1000} km` : `${bar} m`}
              </text>
            </g>
          </svg>
        </div>
      )}
      <ul className="map-legend">
        <li>
          <span className="lg lg-house" />
          Insured house
        </li>
        <li className={zone && geo ? '' : 'is-off'}>
          <span className="lg lg-zone" />
          {geo === undefined ? 'Loading the flood map' : zone ? zoneLabel : 'Flood map not loaded yet'}
        </li>
      </ul>
    </section>
  );
}
