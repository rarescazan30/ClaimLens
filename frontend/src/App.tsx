import { ChevronDown, Moon, Sparkles, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ClaimMenu } from './components/ClaimMenu';
import { listQueue } from './api/hooks';
import type { QueueCase } from './lib/types';
import { Aurora } from './components/Aurora';
import { CaseView } from './components/CaseView';
import { Demo } from './components/Demo';
import { Queue } from './components/Queue';
import { useHashRoute, useTheme } from './lib/hooks';
import { isNewClaim } from './lib/early';
import { APP_NAME } from './lib/meta';

export function App() {
  const [theme, toggleTheme] = useTheme();
  const { path, params } = useHashRoute();
  const caseId = path.match(/^\/case\/([\w-]+)/)?.[1];
  const t = params.get('t');
  const [menuOpen, setMenuOpen] = useState(false);
  const [rows, setRows] = useState<QueueCase[]>([]);
  useEffect(() => {
    listQueue().then(setRows).catch(() => setRows([]));
  }, [caseId]);
  const current = rows.find((r) => r.id === caseId) ?? (caseId ? { id: caseId, claimant: '' } : undefined);
  const waiting = rows.filter((r) => isNewClaim(r.status)).length;

  if (path === '/demo')
    return (
      <>
        <Aurora ground />
        <Demo auto={params.get('auto') === '1'} />
      </>
    );

  return (
    <>
      <Aurora ground />
      <a className="skip" href="#main">
        Salt la conținut
      </a>
      <header className="topbar">
        <div className="topbar-in">
          <a className="brand" href="#/" aria-label={`${APP_NAME}, lista de dosare`}>
            <span className="brand-mark" aria-hidden="true">
              <Sparkles size={17} strokeWidth={1.9} />
            </span>
            {APP_NAME}
          </a>
          <button type="button" className="claim-switcher" onClick={() => setMenuOpen(true)} aria-haspopup="dialog" aria-label="Schimbați dosarul">
            {current ? (
              <>
                <span className="claim-id">{current.id}</span>
                <span className="claim-person">{current.claimant}</span>
              </>
            ) : (
              <>
                <span className="claim-id">Dosare</span>
                <span className="claim-person">{waiting === 0 ? 'niciunul nou' : waiting === 1 ? '1 nou' : `${waiting} noi`}</span>
              </>
            )}
            <ChevronDown size={15} />
          </button>
          <div className="topbar-right">
            <button type="button" className="icon-btn" onClick={toggleTheme} aria-label={theme === 'light' ? 'Temă întunecată' : 'Temă luminoasă'}>
              {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            </button>
          </div>
        </div>
      </header>
      <ClaimMenu open={menuOpen} current={caseId} onClose={() => setMenuOpen(false)} />
      <main id="main">
        {caseId ? <CaseView id={caseId} initialT={t ? Number(t) : undefined} initialTab={params.get('tab') ?? undefined} /> : <Queue />}
      </main>
    </>
  );
}
