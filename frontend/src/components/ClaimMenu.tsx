import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { listQueue } from '../api/hooks';
import { isNewClaim } from '../lib/early';
import { navigate } from '../lib/hooks';
import { OUTCOMES } from '../lib/meta';
import { fmtScore } from '../lib/score';
import type { QueueCase } from '../lib/types';

const stateText = (r: QueueCase) =>
  r.status === 'paused'
    ? 'Paused'
    : r.status === 'received'
    ? 'Ready to investigate'
    : r.status === 'investigating'
      ? 'Investigating'
      : r.score !== undefined && r.outcome
        ? `${fmtScore(r.score)} · ${OUTCOMES[r.outcome].label}`
        : 'Waiting for a decision';

/** Quick switcher: every open claim in one short list. */
export function ClaimMenu({ open, current, onClose }: { open: boolean; current?: string; onClose: () => void }) {
  const [rows, setRows] = useState<QueueCase[]>([]);
  useEffect(() => {
    if (open) listQueue().then(setRows).catch(() => setRows([]));
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const on = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [open, onClose]);
  if (!open) return null;
  const waiting = (r: QueueCase) => Number(isNewClaim(r.status));
  const sorted = [...rows].sort((a, b) => waiting(b) - waiting(a));
  return (
    <>
      <button type="button" className="menu-scrim" onClick={onClose} aria-label="Close claim list" />
      <div className="claim-menu" role="dialog" aria-label="Claims">
        <div className="claim-menu-head">
          <div>
            <span className="eyebrow">Your desk</span>
            <h2>
              {rows.length} claim{rows.length === 1 ? '' : 's'}
            </h2>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="claim-list">
          {sorted.map((r) => (
            <button
              type="button"
              key={r.id}
              className={`claim-row${r.id === current ? ' selected' : ''}`}
              onClick={() => {
                onClose();
                navigate(`#/case/${r.id}`);
              }}
            >
              <span className="avatar">{r.claimant.split(' ').map((w) => w[0]).join('').slice(0, 2)}</span>
              <span className="claim-row-main">
                <strong>{r.claimant}</strong>
                <span>
                  {r.id} · {r.typeLabel} · {r.place}
                </span>
              </span>
              <span className={`claim-state ${waiting(r) ? 'state-investigating' : 'state-ready'}`}>{stateText(r)}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
