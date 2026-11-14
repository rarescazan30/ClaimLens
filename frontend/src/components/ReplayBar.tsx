import { Pause, Play, SkipForward } from 'lucide-react';
import { fmtClock } from '../lib/derive';
import type { RunClock } from '../lib/hooks';
import { STAGES } from '../mock/meta';
import type { CaseFile } from '../mock/types';

const SPEEDS = [1, 2, 4];

export function ReplayBar({ c, run }: { c: CaseFile; run: RunClock }) {
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
          {([['intake', 'Claim'], ['plan', 'Plan'], ['agents', 'Agents'], ['judge', 'Judge'], ['review', 'Decision']] as const).map(([st, label]) => {
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
    </div>
  );
}
