import { Check, CircleAlert, Minus } from 'lucide-react';
import type { KeyboardEvent } from 'react';
import type { LaneState, StageStatus } from '../lib/derive';
import { AGENTS, STAGES } from '../lib/meta';
import type { AgentId, StageId } from '../lib/types';
import { Aurora, type Tone } from './Aurora';
import { AGENT_ICON, STAGE_ICON } from './icons';

const W = 1240;
const H = 310;
const CY = 175;
const R = 14;
const NX: Record<Exclude<StageId, 'agents'>, number> = {
  intake: 110,
  policy: 330,
  plan: 550,
  judge: 990,
  verdict: 1090,
  review: 1190,
};
const LANE_Y = [75, 115, 155, 195, 235, 275];
const LX0 = 650;
const LX1 = 890;
const JR = 17;

const lanePath = (y: number) =>
  `M${NX.plan + R + 2},${CY} C614,${CY} 600,${y} ${LX0},${y} H${LX1} C940,${y} 926,${CY} ${NX.judge - JR - 2},${CY}`;
const LOOP = `M${NX.judge},${CY - JR - 5} C${NX.judge},-10 586,-10 586,${CY - 13}`;

const SEGMENTS: [Exclude<StageId, 'agents'>, Exclude<StageId, 'agents'>][] = [
  ['intake', 'policy'],
  ['policy', 'plan'],
  ['judge', 'verdict'],
  ['verdict', 'review'],
];

const STATUS_TEXT: Record<StageStatus, string> = {
  pending: 'În așteptare',
  running: 'În curs',
  done: 'Finalizat',
  flag: 'Finalizat, cu probleme',
  requeued: 'Se reia în runda următoare',
};

interface Props {
  status: Record<StageId, StageStatus>;
  lanes: Record<AgentId, LaneState>;
  loop: 'unused' | 'active' | 'used';
  /** The round the run is in, for the loop label. */
  round: number;
  active: StageId | null;
  selected: StageId;
  tone: Tone;
  started: boolean;
  onSelect: (stage: StageId, agent?: AgentId) => void;
}

const onKey = (fn: () => void) => (e: KeyboardEvent) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    fn();
  }
};

export function Pipeline({ status, lanes, loop, round, active, selected, tone, started, onSelect }: Props) {
  const focusX = !active ? NX.intake : active === 'agents' ? (LX0 + LX1) / 2 : NX[active];
  const spread = active === 'agents' ? 1.1 : 2.6;

  return (
    <div className="rail">
      <div className="rail-stage">
        <Aurora x={focusX / W} y={CY / H} spread={spread} tone={tone} gain={started ? 1 : 0.35} />
        <svg viewBox={`0 0 ${W} ${H}`} className="rail-svg" role="group" aria-label="Pașii investigației">
          <defs>
            <marker id="loop-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M1 1 L8 5 L1 9" fill="none" stroke="context-stroke" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </marker>
          </defs>

          <g className={`loop is-${loop}`}>
            <path d={LOOP} className="loop-base" markerEnd="url(#loop-arrow)" />
            <path d={LOOP} className="loop-pulse" pathLength={1} />
          </g>

          {SEGMENTS.map(([a, b]) => {
            const s = status[b] !== 'pending' ? 'done' : status[a] === 'running' ? 'running' : 'pending';
            const x0 = NX[a] + (a === 'judge' ? JR : R) + 3;
            const x1 = NX[b] - (b === 'judge' ? JR : R) - 3;
            return (
              <g key={a} className={`seg is-${s}`}>
                <line x1={x0} x2={x1} y1={CY} y2={CY} className="seg-base" />
                <line x1={x0} x2={x1} y1={CY} y2={CY} className="seg-fill" pathLength={1} />
                <line x1={x0} x2={x1} y1={CY} y2={CY} className="seg-pulse" pathLength={1} />
              </g>
            );
          })}

          {AGENTS.map((a, i) => {
            const lane = lanes[a.id];
            const y = LANE_Y[i];
            const d = lanePath(y);
            const pick = () => onSelect('agents', a.id);
            return (
              <g
                key={a.id}
                className={`lane is-${lane.state}${lane.verdict ? ` v-${lane.verdict}` : ''}`}
                style={{ '--i': 6 + i * 0.4 } as React.CSSProperties}
                role="button"
                tabIndex={0}
                aria-label={`${a.name}: ${lane.state === 'done' ? lane.short : lane.state}`}
                onClick={pick}
                onKeyDown={onKey(pick)}
              >
                <path d={d} className="lane-hit" />
                <path d={d} className="lane-base" />
                <path d={d} className="lane-fill" />
                <path d={d} className="lane-pulse" pathLength={1} />
                <text x={LX0 + 20} y={y - 9} className="lane-name">
                  {a.name}
                </text>
                <text x={LX1 - 6} y={y - 9} textAnchor="end" className="lane-note">
                  {lane.state === 'done'
                    ? lane.short
                    : lane.state === 'running'
                      ? lane.round && lane.round > 1
                        ? `Runda ${lane.round}…`
                        : 'Lucrează…'
                      : lane.state === 'skipped'
                        ? 'Nu este necesar'
                        : ''}
                </text>
                {lane.state === 'done' && <circle cx={LX1} cy={y} r={4.5} className="lane-dot" />}
              </g>
            );
          })}
          <text x={(LX0 + LX1) / 2} y={H - 6} textAnchor="middle" className={`lanes-caption${selected === 'agents' ? ' is-selected' : ''}`}>
            Agenți specializați
          </text>

          {STAGES.filter((s) => s.id !== 'agents').map((s) => {
            const id = s.id as Exclude<StageId, 'agents'>;
            const Icon = STAGE_ICON[id];
            const r = id === 'judge' ? JR : R;
            const st = status[id];
            const pick = () => onSelect(id);
            return (
              <g
                key={id}
                className={`node is-${st}${selected === id ? ' is-selected' : ''}`}
                style={{ '--i': STAGES.findIndex((x) => x.id === id) } as React.CSSProperties}
                transform={`translate(${NX[id]} ${CY})`}
                role="button"
                tabIndex={0}
                aria-label={`${s.short}: ${STATUS_TEXT[st]}`}
                aria-pressed={selected === id}
                onClick={pick}
                onKeyDown={onKey(pick)}
              >
                <rect x={-(r + 16)} y={-(r + 16)} width={(r + 16) * 2} height={(r + 16) * 2} rx={r + 8} className="node-hit" />
                <rect x={-(r + 9)} y={-(r + 9)} width={(r + 9) * 2} height={(r + 9) * 2} rx={r * 0.8 + 9} className="node-halo" />
                <rect x={-(r + 5)} y={-(r + 5)} width={(r + 5) * 2} height={(r + 5) * 2} rx={r * 0.8 + 5} className="node-ring" />
                <rect x={-(r + 5)} y={-(r + 5)} width={(r + 5) * 2} height={(r + 5) * 2} rx={r * 0.8 + 5} className="node-spin" pathLength={100} />
                <rect x={-r} y={-r} width={r * 2} height={r * 2} rx={r * 0.62} className="node-disc" />
                <Icon className="node-ico" x={-8} y={-8} width={16} height={16} strokeWidth={2} aria-hidden />
                <text y={r + 25} textAnchor="middle" className="node-label">
                  {s.short}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <ol className="rail-list">
        {STAGES.map((s) => {
          const st = status[s.id];
          const Icon = STAGE_ICON[s.id];
          return (
            <li key={s.id} className={`rl is-${st}${selected === s.id ? ' is-selected' : ''}`}>
              <button type="button" className="rl-row" onClick={() => onSelect(s.id)} aria-pressed={selected === s.id}>
                <span className="rl-dot">
                  {st === 'done' ? <Check size={13} strokeWidth={3} /> : st === 'flag' ? <CircleAlert size={13} strokeWidth={2.6} /> : <Icon size={13} strokeWidth={2.2} />}
                </span>
                <span className="rl-name">{s.short}</span>
                <span className="rl-state">{STATUS_TEXT[st]}</span>
              </button>
              {s.id === 'agents' && (
                <div className="rl-lanes">
                  {AGENTS.map((a) => {
                    const lane = lanes[a.id];
                    const AIcon = AGENT_ICON[a.id];
                    return (
                      <button
                        type="button"
                        key={a.id}
                        className={`chip lane-chip is-${lane.state}${lane.verdict ? ` v-${lane.verdict}` : ''}`}
                        onClick={() => onSelect('agents', a.id)}
                      >
                        {lane.state === 'skipped' ? <Minus size={12} /> : <AIcon size={12} />}
                        {a.name}
                      </button>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
