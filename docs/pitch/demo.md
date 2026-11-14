# Demo-ul live (`#/demo`)

O prezentare pe tot ecranul, în aplicația însăși, în șapte capitole. Capitolul 3 nu este o simulare: pornește dosarul
demo **C-8001** (Mircea Popescu, inundație, Pechea, jud. Galați) pe backend-ul real și arată fiecare pas pe măsură ce se
întâmplă. Toate capitolele, în afară de 3, încap pe un ecran 1920×1080 pe tot ecranul, fără derulare.

| # | Capitol | Ce se vede |
|---|---|---|
| 01 | Problema | 34.000 de locuințe despăgubite într-un an (UNSAR), 20–50 de zile până la plată după o catastrofă (Tractable), 6–7 mii de locuințe afectate în Galați și Vaslui (PAID) |
| – | ClaimIT | Numele și ideea: „Inspectorul nu mai caută dovezi. Primește un dosar cu surse și decide.” |
| 02 | Cum funcționează | Cei cinci pași: dosarul, verificări fără AI, șase agenți, Arbitrul, inspectorul |
| 03 | În direct | Pagina reală a dosarului C-8001, cu o bară de subtitrare care spune ce face sistemul la fiecare pas și un ceas în timp real |
| 04 | Impactul | Timpul manual (estimare, ~150 min) față de durata măsurată adineauri în capitolul 3 plus 10 min de verificare |
| 05 | Încredere | Omul decide, fiecare cifră are o sursă, lipsa datelor nu înseamnă fraudă |
| – | Final | „Daune plătite în zile, nu în săptămâni.” |

## Cum îl porniți

1. Backend-ul **live** (fără `REPLAY=1`), din folderul `backend`. Cheile trebuie să fie în `backend/.env`.
   `RESET_DEMO=1` pornește de la o bază de date curată, cu C-8001 și C-8002 neanalizate. Folosiți-l o dată, chiar
   înainte de prezentare, ca investigația din capitolul 3 să pornească singură, de la zero.

   Mac sau Linux:

   ```bash
   RESET_DEMO=1 .venv/bin/uvicorn app.main:app --port 8000
   ```

   Windows:

   ```bash
   set PYTHONUTF8=1&& set RESET_DEMO=1&& .venv\Scripts\uvicorn app.main:app --port 8000
   ```

   Dacă backend-ul repornește mai târziu, porniți-l fără `RESET_DEMO=1`, ca să nu pierdeți rularea deja făcută.

2. Frontend-ul, din folderul `frontend`:

   ```bash
   npm run dev
   ```

3. Deschideți **http://localhost:5173/#/demo** și apăsați **F** pentru ecran complet.

## Comenzi

| Tastă | Ce face |
|---|---|
| → sau spațiu | Capitolul următor. În capitolul 3, după ce investigația s-a terminat, prima apăsare deschide raportul. |
| ← | Capitolul anterior (sau înapoi de la raport la pagina dosarului) |
| F | Ecran complet |
| Esc | Ieșire din demo, înapoi la lista de dosare |

Varianta fără mâini: **http://localhost:5173/#/demo?auto=1**. Capitolele avansează singure, iar capitolul 3 așteaptă
investigația, arată raportul și merge mai departe.

## Ce trebuie știut înainte de prezentare

- **Prima intrare în capitolul 3 pornește investigația singură**, dacă dosarul nu a mai fost investigat. Dacă a fost,
  bara arată „Investigație încheiată”, durata reală a ultimei rulări și două butoane: „Vedeți raportul” și „Rulați din
  nou, în direct”.
- **O rulare live durează în jur de 2–3 minute** și consumă puțin credit AI. Măsurat azi: 2 min 36 s și 1 min 57 s.
- **Scorul poate diferi de la o rulare la alta**, pentru că răspunsurile AI nu sunt identice: azi 47,8 și 63,6, cu
  aceeași recomandare (analiză standard). Nu promiteți un scor exact în pitch.
- **Depinde de internet și de sursele externe.** Dacă o sursă nu răspunde (de exemplu GDELT), agentul o marchează și
  investigația continuă cu celelalte.
- **Plasă de siguranță:** rulați C-8001 o dată înainte de prezentare. Dacă în timpul pitch-ului internetul cade, capitolul
  3 arată rularea deja făcută, cu durata ei reală, și puteți deschide raportul.
- **Pentru o înregistrare video:** pe Windows, Win+Alt+R pornește și oprește înregistrarea ferestrei (Xbox Game Bar),
  cu demo-ul în varianta `?auto=1`.
