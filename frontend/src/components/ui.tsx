import { Check, CircleAlert, Info, Minus, X } from 'lucide-react';
import { useCountUp } from '../lib/hooks';
import { BANDS, OUTCOMES } from '../lib/meta';
import { fmtScore } from '../lib/score';
import type { Band, Outcome, Photo, Status, Verdict } from '../lib/types';

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

export function BandPill({ score, band }: { score: number; band: Band }) {
  return (
    <span className={`band-pill b-${band}`}>
      <b>{fmtScore(score)}</b>
      {BANDS[band].label}
    </span>
  );
}

export function OutcomeTag({ outcome }: { outcome: Outcome }) {
  return <span className={`route-tag r-${outcome}`}>{OUTCOMES[outcome].label}</span>;
}

/** The claimant's photos, as served by the backend, with the forensic agent's checks once they are known. */
export function PhotoGrid({ photos, t }: { photos: Photo[]; t: number }) {
  if (!photos.length) return <Empty title="No photos on this claim" body="The claim was filed without photos, so there is nothing for the photo checks to look at." />;
  return (
    <ul className="photos">
      {photos.map((p) => {
        const known = t >= p.at;
        return (
          <li key={p.name} className={`photo${known ? ` s-${p.status}` : ' is-waiting'}`}>
            <div className="photo-thumb is-real">
              <img src={p.url} alt={`Claimant photo ${p.name}`} loading="lazy" />
              {known && <StatusIcon status={p.status} />}
            </div>
            <div className="photo-meta">
              <span className="mono">{p.name}</span>
              {known ? p.notes.map((n) => <span key={n} className="photo-note">{n}</span>) : <span className="photo-note">Not checked yet</span>}
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
