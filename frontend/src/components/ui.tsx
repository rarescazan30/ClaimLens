import { Check, CircleAlert, Info, Minus, X } from 'lucide-react';
import { useCountUp } from '../lib/hooks';
import { bandOf } from '../lib/score';
import { BANDS, ROUTES } from '../mock/meta';
import type { Photo, Route, Status, Verdict } from '../mock/types';

export function StatusIcon({ status }: { status: Status }) {
  const Icon = status === 'ok' ? Check : status === 'flag' ? CircleAlert : status === 'fail' ? X : Info;
  const label = status === 'ok' ? 'Passed' : status === 'flag' ? 'Flagged' : status === 'fail' ? 'Failed' : 'Note';
  return (
    <span className={`status-ico s-${status}`} role="img" aria-label={label}>
      <Icon size={12} strokeWidth={3} />
    </span>
  );
}

/** Numbered kicker above a headline: "03 —— Round-ups". */
export function Kicker({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <p className="kicker">
      <span className="kicker-n">{n}</span>
      <span className="kicker-line" aria-hidden="true" />
      <span className="kicker-label">{children}</span>
    </p>
  );
}

/** A figure that counts up when it appears. */
export function CountUp({ value }: { value: number }) {
  return <>{Math.round(useCountUp(value))}</>;
}

const VERDICT_TEXT: Record<Verdict, string> = {
  supports: 'Supports the claim',
  contradicts: 'Contradicts the claim',
  inconclusive: 'Inconclusive',
};

export function VerdictChip({ verdict }: { verdict: Verdict }) {
  const Icon = verdict === 'supports' ? Check : verdict === 'contradicts' ? X : Minus;
  return (
    <span className={`chip v-${verdict}`}>
      <Icon size={12} strokeWidth={3} />
      {VERDICT_TEXT[verdict]}
    </span>
  );
}

export function BandPill({ score }: { score: number }) {
  const band = bandOf(score);
  return (
    <span className={`band-pill b-${band}`}>
      <b>{score}</b>
      {BANDS[band].label}
    </span>
  );
}

export function RouteTag({ route }: { route: Route }) {
  return <span className={`route-tag r-${route}`}>{ROUTES[route].label}</span>;
}

/** Latest known state of a photo at timeline offset `t`, or null if not yet processed. */
export function photoState(p: Photo, t: number) {
  const seen = p.states.filter((s) => s.at <= t);
  return seen.length ? seen[seen.length - 1] : null;
}

export function PhotoGrid({ photos, t }: { photos: Photo[]; t: number }) {
  return (
    <ul className="photos">
      {photos.map((p) => {
        const s = photoState(p, t);
        return (
          <li key={p.id} className={`photo${s ? ` s-${s.status}` : ' is-waiting'}`}>
            <div className="photo-thumb" style={{ '--hue': p.hue } as React.CSSProperties}>
              {s && <StatusIcon status={s.status} />}
            </div>
            <div className="photo-meta">
              <span className="mono">{p.name}</span>
              <span>{s ? s.taken : 'Waiting'}</span>
              <span className="photo-note">{s ? s.note : 'Not checked yet'}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      <p>{body}</p>
    </div>
  );
}
