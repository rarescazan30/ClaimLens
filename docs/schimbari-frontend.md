# Schimbări în frontend (față de `main`, commit `69823e7`)

Acest document descrie tot ce s-a schimbat în interfață față de ce era în repo la commit-ul `69823e7`
(„Merge rc/readme”), același cu `origin/main` la momentul scrierii.

## Pe scurt

- **Backend-ul nu a fost atins.** Nicio modificare în `backend/`, `demo/` (inclusiv răspunsurile salvate din
  `demo/cache/`) sau `data-fabric/`. Demo-ul cu `REPLAY=1` dă exact aceleași răspunsuri, scoruri și recomandări
  ca înainte.
- **Toate schimbările sunt în `frontend/`:** 20 de fișiere, dintre care unul șters (`ReplayBar.tsx`).
- **Testele trec** (19 din 19, `npm test`), iar **build-ul de producție merge** (`npm run build`).

Ce s-a schimbat, pe teme:

1. Tema de culori: fundal mai închis și mai neutru, carduri mai vizibile, fără strălucire.
2. Toată interfața este în română, cu formulări firești și formatul românesc pentru numere și date.
3. Bara de derulare (slider-ul) de sub diagramă a fost scoasă, la fel și bara subțire de progres de jos.
4. Diagrama investigației: liniile dintre pași se văd și înainte de pornire, iar eticheta rundei a fost scoasă.
5. Raportul complet: secțiuni pliabile, aranjate pe două coloane echilibrate, fără scorul afișat de două ori.
6. Pagina unui dosar încheiat încape pe un ecran 1920×1080 până la verdict.

---

## Cum verificați că backend-ul este neatins

Din folderul `ClaimLens`:

```bash
git diff --stat HEAD -- backend demo data-fabric
```

Comanda nu trebuie să afișeze nimic. Lista completă a fișierelor schimbate:

```bash
git status -s
```

Toate liniile trebuie să înceapă cu `frontend/`. Singura excepție este `.claude/`, un fișier local de pornire
a serverelor, care nu face parte din proiect și nu trebuie inclus în commit.

---

## 1. Tema de culori

Fișier: `frontend/src/styles.css`. Toate schimbările de stil sunt **adăugate la finalul fișierului**, în
blocuri cu comentarii. Nimic din stilurile existente nu a fost șters sau rescris, deci orice bloc poate fi
scos separat dacă nu mai e dorit.

| Ce | Înainte | Acum |
|---|---|---|
| Fundal (tema întunecată, cea implicită) | violet foarte închis, `#13111b` | negru-gri neutru, `#16171b` |
| Lumina mov din spatele paginii | puternică | redusă la aproximativ o treime |
| Carduri | margine abia vizibilă | margine clară și umbră, o treaptă mai deschise decât fundalul |
| Strălucire la hover pe carduri și butoane | da | nu |
| Accentul violet (titluri, butoane, cifre) | neschimbat | neschimbat |

Detalii:

- Titlurile au aceeași familie de font, puțin mai ferme și mai puțin înghesuite.
- Pe cardurile din lista de dosare, data avizării stă acum sub nume, nu lângă el, ca numele să nu se mai rupă
  pe trei rânduri.
- **Corectat un bug introdus pe parcurs:** valorile pentru tema luminoasă suprascriau din greșeală tema
  întunecată, așa că liniile diagramei și marginile cardurilor se desenau închis pe fundal închis, adică
  invizibil. Ordinea a fost corectată.

## 2. Interfața în română

Fișiere: aproape toate componentele din `frontend/src/components/`, plus `src/lib/meta.ts`,
`src/lib/derive.ts`, `src/api/build.ts`, `src/api/client.ts`, `src/App.tsx` și `index.html`.

- **Ton formal**, potrivit pentru o aplicație oficială: „Aprobați”, „Deschideți dosarul”, „Reluați
  investigația”.
- **Numere și date în format românesc:** `79,5`, `14.500 RON`, `28 nov. 2023`.
  - `fmtScore` din `src/lib/score.ts` folosește acum virgula zecimală.
  - `src/api/build.ts` formatează numerele cu `toLocaleString('ro-RO')` și datele cu locale-ul `ro-RO`.
- **Pluralele sunt corecte:** „1 agent”, „3 agenți”, „20 de agenți”. Pentru asta există o funcție nouă,
  `nr(n, singular, plural)`, în `src/lib/meta.ts`.
- **Pagina:** `<html lang="ro">`, iar titlul este „AsigIT · Dosare de daună”.
- **Denumiri noi:** toate se schimbă dintr-un singur loc, `src/lib/meta.ts`.

| Înainte | Acum |
|---|---|
| Judge | Arbitru |
| Claim / Policy check / Plan / Agents / Verdict / Review | Dosar / Poliță / Plan / Agenți / Verdict / Decizie |
| Weather, Satellite, Risk zones, Photo forensics, Street view, Local news | Meteo, Satelit, Zone de risc, Analiză foto, Imagini stradale, Presă locală |
| Fast-track / Standard review / Antifraud referral | Plată rapidă / Analiză standard / Antifraudă |
| Very likely / Likely / Uncertain / Unlikely | Foarte plauzibil / Plauzibil / Incert / Puțin plauzibil |

Exemple de formulări:

| Unde | Înainte | Acum |
|---|---|---|
| Titlul listei | Strongest claims, paid first. | Dosarele cele mai sigure, primele la plată. |
| Dosar nou | Ready to investigate. | Dosarul așteaptă investigația. |
| Dosar încheiat | Waiting for your decision. | Decizia vă aparține. |
| Scor de pornire | Starts at 50 | Scor inițial: 50 (cu explicație la hover) |

**Ce nu s-a tradus:** textele scrise de AI (constatările agenților, explicațiile Arbitrului, motivul
verdictului). Ele vin din backend și erau deja în română. Nu au fost schimbate, pentru că orice modificare a
instrucțiunilor AI ar invalida răspunsurile salvate în `demo/cache/` și ar cere o reînregistrare live.

**Teste:** în `src/api/build.test.ts`, șase rezultate așteptate au fost actualizate la textul în română
(de exemplu, `'90.4 km/h gusts'` a devenit `'Rafale de 90,4 km/h'`). Logica testată este aceeași.

## 3. Slider-ul și bara de progres, scoase

- **Șters:** `src/components/ReplayBar.tsx`, adică bara cu play/pauză, slider, viteză (1×/2×/4×) și
  „Run again”. Pașii se văd acum dând click pe ei în diagramă.
- **Mutate lângă butonul principal din `CaseView.tsx`:**
  - „Treceți la verdict”, cât timp se redă o investigație.
  - „Reluați investigația”, după final. Cere în continuare confirmare înainte să șteargă rezultatul.
- **Scos:** scurtătura ascunsă din tastatură (Space = play/pauză), pentru că nu mai există niciun control
  vizibil pentru redare.
- **Scoasă:** bara subțire de progres din partea de jos a paginii (`.run-progress`).
- **Neschimbat:** redarea automată a unei investigații proaspăt rulate funcționează la fel.

## 4. Diagrama investigației

Fișier: `src/components/Pipeline.tsx`, plus stiluri în `styles.css`.

- **Liniile dintre pași** (Dosar → Poliță → Plan → cei șase agenți → Arbitru → Verdict → Decizie, plus
  săgeata de întoarcere a Arbitrului) se văd și înainte de pornirea investigației.
- **Scoasă:** eticheta de deasupra săgeții („Runda 2 · verificări suplimentare”, respectiv „Arbitrul poate
  trimite agenții înapoi”). Fiecare rând de agent își păstrează rezultatul.
- **Rezultate mai scurte pe rândurile agenților**, ca să nu se suprapună cu numele: „Imagine din 2012-07”,
  „Fără fotografii”. Varianta lungă apare în raport.
- **Înălțime limitată:** pe ecrane foarte late, diagrama nu mai crește peste 300 px.

## 5. Raportul complet

Fișiere: `src/components/Report.tsx` și `src/components/CaseView.tsx`.

- **„Ce a influențat scorul”** este acum o secțiune pliabilă, închisă la început, ca „Cum s-a ajuns la
  verdict” și „Fotografiile depuse”.
- **Două coloane:** în stânga cele trei secțiuni pliabile, în dreapta „Condiții obligatorii”. Când secțiunile
  sunt închise, coloanele se termină la aceeași înălțime.
- **Scorul nu mai apare de două ori:** cât timp raportul este deschis, cardul-rezumat de sub diagramă (scor,
  verdict, „Aprobați”, „Vedeți de ce”) este ascuns, pentru că raportul conține deja toate aceste informații.

## 6. Încadrarea pe ecran (1920×1080)

Fișiere: `src/components/CaseView.tsx` și `styles.css`.

- **Un singur rând deasupra dosarului:** „← Lista de dosare”, tipul și localitatea, suma și data avizării, iar
  în dreapta starea investigației. Pe ecrane înguste rândul trece pe mai multe linii.
- **Antet compact după ce investigația s-a încheiat:**
  - Rândul cu ceasul redării („07 — Decizie · 00:22 · runda 2”) este ascuns.
  - Fraza de sub titlu a fost scoasă.
  - Titlul este mai mic.
- **Cardul cu verdictul din raport:** margini mai mici, scorul puțin mai mic, iar explicația folosește toată
  lățimea coloanei.
- **Cât timp investigația rulează,** antetul rămâne mare, ca înainte.
- **Măsurat la 1920×1080:**
  - Cardul-rezumat se termină la 932 px.
  - Cardul cu verdictul din raport se termină la 1003 px.

---

## Lista fișierelor

| Fișier | Ce s-a schimbat |
|---|---|
| `frontend/index.html` | `lang="ro"`, titlul și descrierea paginii |
| `frontend/src/App.tsx` | Bara de sus în română |
| `frontend/src/api/build.ts` | Textele construite din date, în română; numere și date în format `ro-RO` |
| `frontend/src/api/build.test.ts` | Rezultatele așteptate, actualizate la română |
| `frontend/src/api/client.ts` | Mesajul „serverul nu răspunde”, în română |
| `frontend/src/components/Cards.tsx` | Cardurile de scor, dosar și hartă, în română |
| `frontend/src/components/CaseView.tsx` | Fără slider și bară de progres; butoanele mutate; un singur rând de context; antet compact; rezumatul ascuns cu raportul deschis; în română |
| `frontend/src/components/ClaimMenu.tsx` | Lista rapidă de dosare, în română |
| `frontend/src/components/DecisionPanel.tsx` | Panoul de decizie, în română |
| `frontend/src/components/EvidenceDrawer.tsx` | Panoul cu dovezile unui agent, în română |
| `frontend/src/components/Pipeline.tsx` | Fără eticheta rundei; în română |
| `frontend/src/components/Queue.tsx` | Lista de dosare, în română |
| `frontend/src/components/ReplayBar.tsx` | **Șters** |
| `frontend/src/components/Report.tsx` | Secțiune pliabilă pentru scor; două coloane; „Scor inițial”; în română |
| `frontend/src/components/StageDetail.tsx` | Detaliile pașilor, în română |
| `frontend/src/components/ui.tsx` | Etichete mici (stări, fotografii), în română |
| `frontend/src/lib/derive.ts` | Un mesaj, în română |
| `frontend/src/lib/meta.ts` | Toate denumirile în română; funcția nouă `nr()` pentru plurale |
| `frontend/src/lib/score.ts` | Scor cu virgulă zecimală |
| `frontend/src/styles.css` | Blocuri noi la final: tema, cardurile, liniile diagramei, raportul, încadrarea pe ecran |

## De știut

- **Pornirea backend-ului pe Windows:** numele cu diacritice („Persoană Sintetică”) apar stricate
  („PersoanÄƒ”) dacă backend-ul nu este pornit cu UTF-8. Aceasta nu este o schimbare din acest lucru, ci o
  problemă existentă a backend-ului pe Windows. Soluția temporară este să-l porniți cu `PYTHONUTF8=1`:

  ```bash
  set PYTHONUTF8=1&& set REPLAY=1&& .venv\Scripts\uvicorn app.main:app --port 8000
  ```

  Rezolvarea de fond, care rămâne de făcut separat, este ca backend-ul să deschidă fișierele cu
  `encoding="utf-8"`.
- **Cod rămas nefolosit, inofensiv:**
  - Stilurile vechi ale barei de redare (`.replay`, `.scrub`) au rămas în `styles.css`.
  - Proprietatea `round` a componentei `Pipeline` nu mai este folosită.
  - Ambele pot fi curățate oricând.
- **Fișiere locale care nu intră în commit:** `.claude/launch.json` (pornirea serverelor) și `backend/uv.lock`
  (dacă reapare).
