import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { navigate } from '../lib/hooks';
import { listQueue } from '../mock/api';
import { ROUTES } from '../mock/meta';
import type { QueueCase } from '../mock/types';

/** Quick switcher: every open claim in one short list. */
export function ClaimMenu({ open, current, onClose }: { open: boolean; current?: string; onClose: () => void }) {
  const [rows, setRows] = useState<QueueCase[]>([]);
  useEffect(() => {
    listQueue().then(setRows);
  }, []);
  useEffect(() => {
    if (!open) return;
    const on = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [open, onClose]);
  if (!open) return null;
  const sorted = [...rows].sort((a, b) => Number(b.status === 'new') - Number(a.status === 'new'));
  return (
    <>
      <button type="button" className="menu-scrim" onClick={onClose} aria-label="Close claim list" />
      <div className="claim-menu" role="dialog" aria-label="Open claims">
        <div className="claim-menu-head">
          <div>
            <span className="eyebrow">Your desk</span>
            <h2>{rows.length} open claims</h2>
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
              <span className="avatar">{r.claimant.split(' ').map((w) => w[0]).join('')}</span>
              <span className="claim-row-main">
                <strong>{r.claimant}</strong>
                <span>
                  {r.id} · {r.typeLabel} · {r.place}
                </span>
              </span>
              <span className={`claim-state ${r.status === 'verdict' ? 'state-ready' : 'state-investigating'}`}>
                {r.status === 'verdict' && r.route ? `${r.score} · ${ROUTES[r.route].label}` : 'Ready to investigate'}
              </span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
