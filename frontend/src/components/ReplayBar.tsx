import { Pause, Play, RotateCcw, SkipForward } from 'lucide-react';
import { useState } from 'react';
import { fmtClock } from '../lib/derive';
import type { RunClock } from '../lib/hooks';
import { STAGES } from '../lib/meta';
import type { CaseFile } from '../lib/types';

const SPEEDS = [1, 2, 4];

/**
 * Replay controls for a finished run, plus "Run again" (POST /rerun).
 * While a run is live there is nothing to scrub, so only the clock shows.
 */
export function ReplayBar({ c, run, live, busy, onRerun }: { c: CaseFile; run: RunClock; live: boolean; busy: boolean; onRerun: () => void }) {
  const [arming, setArming] = useState(false);
  if (live)
    return (
      <div className="replay is-live">
        <span className="live-dot is-on" />
        <span className="clock">{fmtClock(run.time)}</span>
        <span className="replay-live-note">Live. The replay opens when the investigation ends.</span>
      </div>
    );
  const pct = (run.time / c.duration) * 100;
  const atEnd = run.time >= c.duration;
  const stageNow = STAGES.find((s) => s.id === [...c.windows].reverse().find((w) => w.at <= run.time)?.stage)?.short ?? 'Start';
  return (
    <div className="replay">
      <button type="button" className="icon-btn is-solid" onClick={run.toggle} aria-label={run.playing ? 'Pause' : atEnd ? 'Replay from the start' : 'Play'}>
        {run.playing ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" />}
      </button>
      <span className="clock">
        {fmtClock(run.time)} <span>/ {fmtClock(c.duration)}</span>
      </span>
      <div className="scrub">
        <div className="scrub-track">
          <div className="scrub-fill" style={{ width: `${pct}%` }} />
          {c.windows.slice(1).map((w) => (
            <span key={`${w.stage}-${w.at}`} className="scrub-tick" style={{ left: `${(w.at / c.duration) * 100}%` }} />
          ))}
        </div>
        <div className="scrub-labels" aria-hidden="true">
          {([['intake', 'Claim'], ['plan', 'Plan'], ['agents', 'Agents'], ['judge', 'Judge']] as const).map(([st, label]) => {
            const w = c.windows.find((x) => x.stage === st);
            return w ? (
              <span key={st} style={{ left: `${(w.at / c.duration) * 100}%` }}>
                {label}
              </span>
            ) : null;
          })}
        </div>
        <input
          type="range"
          min={0}
          max={c.duration}
          step={100}
          value={Math.round(run.time)}
          onChange={(e) => run.seek(Number(e.target.value))}
          aria-label="Replay position"
          aria-valuetext={`${fmtClock(run.time)}, ${stageNow}`}
        />
      </div>
      <button
        type="button"
        className="btn btn-quiet speed-btn"
        onClick={() => run.setSpeed(SPEEDS[(SPEEDS.indexOf(run.speed) + 1) % SPEEDS.length])}
        aria-label={`Playback speed ${run.speed} times. Change speed`}
        title="Change speed"
      >
        {run.speed}×
      </button>
      {!atEnd && (
        <button type="button" className="btn btn-quiet" onClick={run.finish}>
          Skip to verdict
          <SkipForward size={14} />
        </button>
      )}
      {atEnd &&
        (arming ? (
          <>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => { setArming(false); onRerun(); }}>
              Erase this run and start over
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setArming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => setArming(true)} title="Investigate this claim again from the start">
            <RotateCcw size={14} />
            Run again
          </button>
        ))}
    </div>
  );
}
