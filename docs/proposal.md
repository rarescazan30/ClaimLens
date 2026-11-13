# ClaimLens — workflow unificat + research (UiPath Hackathon)

13 Nov 2026 · propunerea inițială a echipei (copie de lucru; sursa e documentul Claude Docs al echipei)

## TL;DR

Construim un asistent agentic pentru evaluatorul de daune al unui asigurător (locuințe, dezastre naturale). „ClaimLens” e doar un nume de lucru.

1. Dosarul intră (cerere + poliță + poze). Sistemul extrage datele și verifică automat cererea față de poliță și autenticitatea pozelor.
2. Un Orchestrator face un plan în funcție de tipul daunei și lansează agenți specialiști în paralel: meteo, satelit, street view, știri locale, zone de risc și foto-forensic.
3. Un Judge separat cântărește dovezile. Unde lipsesc date sau dovezile se contrazic, trimite agenții înapoi cu întrebări precise (maxim 3 runde).
4. Rezultatul e un scor de plauzibilitate, factorii care l-au produs, sursele și o recomandare. Dosarele solide merg pe fast-track, cele suspecte primesc mai mult timp uman.
5. Evaluatorul vede tot raționamentul pas cu pas, poate corecta și aprobă decizia. **AI-ul nu respinge niciodată singur un dosar.**

**Termen:** sâmbătă, 14 noiembrie, ora 14:00 — cod pe GitHub, prototip funcțional, pitch de 5 minute și demo de până la 5 minute.

## Problema, utilizatorul și valoarea

Utilizatorul principal e **evaluatorul de daune**. Utilizatori secundari: șeful departamentului de daune (prioritizează coada) și echipa antifraudă (SIU).

**Problema.** Pentru fiecare dosar, evaluatorul caută manual meteo, hărți, imagini și știri ca să judece dacă dauna e plauzibilă. În valurile de dezastre volumul explodează exact când timpul e cel mai scurt. Pentru PAD, asigurătorul are maximum 5 zile ca să trimită un reprezentant la constatare.

**Miza financiară.** Insurance Europe estimează frauda (detectată + nedetectată) la circa 10% din cheltuielile cu daune în Europa. În 2017 s-au detectat 2,5 mld. € din circa 13 mld. € estimate.

**Valoarea:**
- Pentru clientul onest: dosarele cu dovezi solide trec pe fast-track, banii ajung mai devreme.
- Pentru asigurător: frauda documentară (poze reciclate, metadate false) și daunele incompatibile cu evenimentul real sunt marcate cu dovezi, nu doar cu un scor opac.

> „Evaluatorul nu mai face research. Primește un dosar de dovezi cu surse și decide el.”

## Workflow-ul unificat, pe etape

Regula de design: ce e verificabil prin reguli se face determinist, ce cere judecată și căutare se face cu agenți. Etapele 1–3 sunt fixe; etapele 4–6 se schimbă de la caz la caz.

1. **Intake.** Cerere, poliță, adresă, data evenimentului, poze → caz cu ID unic. *(UiPath Apps / email → Maestro Case)*
2. **Parsare și validare.** CNP titular, adresă, perioada de valabilitate, riscuri acoperite, sumă asigurată. Datele lipsă generează automat o cerere către client. *(IXP)*
3. **Cross-check poliță ↔ cerere (determinist):** poliță activă + perioada de așteptare trecută; risc acoperit (PAD: cutremur, inundații, alunecări de teren); adresa coincide; notificare în termen (PAD: max. 60 de zile). O regulă eșuată nu respinge cazul — îl marchează și îl trimite la om cu motivul. *(API workflow + reguli în Maestro)*
4. **Foto-forensic** (prima poartă agentică): EXIF vs. data și adresa declarate, poze reciclate, semne de imagine generată, poza arată chiar dauna declarată.
5. **Planul Orchestratorului.** Ipoteze testabile („rafale ≥ 70 km/h la adresă, pe 12.11”), alegerea agenților, întrebări precise. Planul e afișat în UI.
6. **Investigația în buclă.** Agenți în paralel, output standard. Judge-ul re-trimite doar agentul relevant. Max. 3 runde sau stop când scorul nu se mai schimbă.
7. **Construirea cazului.** Scor, cei 5 factori, dovezi cu surse și dată, poze cu interpretare, recomandare: fast-track / evaluare standard / antifraudă. Coadă sortată.
8. **Decizia umană.** Aprobă, modifică sau cere investigație suplimentară (human-in-the-loop). Orice abatere de la recomandare se salvează cu motivul. *(Action Center / Case App)*
9. **Învățarea.** Amprenta evenimentului (poligon inundat, maxime meteo) se salvează în knowledge base și se refolosește.

**Demo, două cazuri cap-coadă:**
- **Caz cinstit:** acoperiș smuls într-o furtună reală → fast-track.
- **„Fraudă inteligentă”:** casa e la 150 m de poligonul inundat, dar cu 6 m mai sus → după runda 2, trimitere la antifraudă.

## Agenții specialiști

Fiecare agent: o singură competență, o listă închisă de unelte, un buget de pași (ex. max. 6 apeluri de unelte pe rundă). Se oprește la încredere peste prag sau la buget epuizat, și spune explicit ce i-a lipsit.

| Agent | Întrebarea | Date / API-uri | Ce returnează |
| --- | --- | --- | --- |
| Meteo | A existat fenomenul, la adresă, la data declarată, cu intensitatea necesară? | Open-Meteo Historical (ERA5 ~25 km din 1940, ERA5-Land ~9 km), Historical Forecast API, avertizări ANM | Rafala max. (km/h), precipitații 24/72 h (mm), zăpadă (cm) vs. pragul tipului de daună |
| Satelit | Zona a fost efectiv inundată? | Copernicus GFM (Sentinel-1 SAR, REST, arhivă din 2015), Sentinel-2, CEMS Rapid Mapping | Casa în/în afara poligonului, distanța (m), ziua trecerii satelitului |
| Street view | Cum arăta casa înainte? Dauna era preexistentă? | Street View metadata, Mapillary, ortofoto istoric | Data imaginii, starea acoperișului/fațadei, comparația cu pozele clientului |
| Știri locale | Există confirmări independente? | Web search, GDELT, ISU/IGSU, primării | Evenimente confirmate cu loc, oră, sursă, link |
| Zone de risc | Casa e plauzibil expusă? | OSM (distanța la apă), Copernicus DEM, hărți hazard ANAR, EGMS (InSAR) | Distanța la râu (m), diferența de nivel (m), zona de hazard, deplasare teren (mm/an) |
| Foto-forensic | Pozele sunt autentice, recente, relevante? | EXIF, căutare inversă, C2PA, LLM de viziune | Verdict per poză |

Formatul standard de output: vezi [`docs/contracts.md`](contracts.md). `strength` = cât schimbă dovada verdictul; `data_quality` = cât ne putem baza pe sursă. Sunt separate pentru că Judge-ul le folosește diferit.

## Orchestrator + Judge

Două roluri separate: Orchestratorul planifică și trimite agenții, Judge-ul evaluează și decide dacă mai e nevoie de investigație (un agent care își judecă propriul plan tinde să își confirme ipotezele).

La fiecare rundă, Judge-ul:
1. Marchează fiecare ipoteză: confirmată / infirmată / neconcludentă / în conflict.
2. Pentru fiecare gol sau conflict formulează o întrebare îngustă pentru un singur agent.
3. Se oprește dacă: toate ipotezele critice au verdict; scorul s-a mișcat < 5 puncte; 3 runde; buget de timp/cost depășit.

**Erori și date lipsă:** retry o dată, apoi sursa alternativă, apoi `inconclusive` cu golul scris explicit. Un gol nu înseamnă „fraudă” — scade încrederea și duce cazul spre om.

### Cei 5 factori

| Factor | Ce măsoară | Cine îl produce | Tip |
| --- | --- | --- | --- |
| F1. Acoperire și conformitate | Poliță activă, risc acoperit, adresă și termen corecte | Reguli deterministe | Poartă |
| F2. Autenticitatea dovezilor | Poze/documente reale, recente, de la adresă | Foto-forensic | Poartă la fals clar, altfel scor |
| F3. Confirmarea evenimentului | Fenomenul s-a întâmplat acolo și atunci | Meteo, satelit, știri | Scor |
| F4. Consistența cauză–daună | Intensitatea și expunerea pot produce dauna; nu era preexistentă | Zone de risc, street view, meteo | Scor |
| F5. Semnale contextuale | Întârzierea notificării, suma vs. valoarea locuinței, istoricul | Reguli + date interne | Scor, pondere mică |

**Combinarea prin log-odds:**

```
logit(P) = logit(P0) + Σ_i  w[t,i] · s_i · q_i · d_i
```

`w` = ponderea asigurătorului pentru tipul de daună `t`; `s` = strength; `q` = data_quality; `d` = +1 susține / −1 contrazice / 0 neconcludent.

Benzi: foarte probabil (≥ 85), probabil (65–85), incert (35–65), improbabil (< 35). Denumire: **„scor de plauzibilitate a daunei”**, nu „probabilitatea ca firma să plătească”.

**Ponderi per firmă — cinci corecții:** (1) ponderi per tip de daună × agent (profile: inundație, furtună, alunecare, greutatea zăpezii; cutremurul are formulă separată); (2) F1 și falsurile clare din F2 sunt porți, nu termeni în sumă; (3) `w` (preferința firmei) separat de `q` (calitatea per caz); (4) sursele corelate nu se numără de două ori — Judge-ul marchează sursa primară; (5) ponderile se calibrează pe dosare închise (backtesting). Ponderile schimbă doar prioritizarea și recomandarea, niciodată decizia.

## Maparea pe produsele UiPath

| Piesă | Produs UiPath | Cum îl folosim |
| --- | --- | --- |
| Ciclul de viață al cazului | Maestro Case (alternativ Maestro BPMN) | Cele 9 etape, bucla ca re-entry pe etapa 6 |
| Extragere cerere + poliță | IXP | Câmpuri cu scoruri de încredere; încredere mică → validare umană |
| Agenții specialiști | Agent Builder (Studio Web) | Prompt, tools, contexts, escalations |
| Orchestrator + Judge | Coded agent (Python + LangGraph, `uipath-langchain`) | Bucla plan → dispatch → judge → re-dispatch |
| API-uri externe | API workflows / Integration Service / Swagger MCP Server | Open-Meteo, GFM, Street View, Overpass ca unelte |
| Condiții de poliță | Context Grounding | Agenții citează clauza relevantă |
| Cazuri, dovezi, scoruri, KB | Data Fabric | Claim, Evidence, TraceStep, EventFootprint, WeightConfig |
| Decizia umană | Action Center / Case App | Aprobare, modificare, investigație suplimentară |
| UI evaluator | UiPath Apps sau front-end propriu peste Data Fabric | Coadă, ecranul cazului, trace vizual |
| Observabilitate | Agent traces + Evaluations | 10 dosare sintetice, trajectory + faithfulness |

**Pragmatic pentru noaptea asta:** un agent complet (meteo) + unul pentru satelit sau zone de risc. Restul cu date pre-capturate, menționat explicit în pitch. Mai bine 2 agenți reali și o buclă reală decât 6 falși.

## Reasoning trace vizual și controlul evaluatorului

Fiecare pas scrie un eveniment structurat (vezi [`docs/contracts.md`](contracts.md)), iar UI-ul le afișează:
- Timeline-ul etapelor, fiecare cu stare, deschidere la click.
- Benzi paralele per agent, per rundă: ipoteză, apeluri de unelte, rezultat, surse.
- Decizia Judge-ului în clar.
- Hartă: casa, poligonul inundat, distanța; pozele cu verdict.
- Graficul de contribuții, dovadă cu dovadă.
- Replay: slider pas cu pas.

Evaluatorul poate: corecta un câmp (cazul se reia de la etapa afectată), respinge o dovadă (Judge recalculează), pune o întrebare liberă (devine task de agent), aproba acțiunile importante.

## Criteriile juriului

| Criteriu | Puncte | Ce arătăm |
| --- | --- | --- |
| Working result | 30 | Un dosar real intră și iese cu verdict, dovezi și surse, live + al doilea înregistrat |
| User value | 25 | „40 de minute de research” → „2 minute de verificat”; plată mai rapidă |
| Agent design | 20 | Re-dispatch real; API căzut cu fallback vizibil; date lipsă → inconclusive |
| Originality | 15 | Dosar de dovezi din surse publice; KB pe evenimente |
| Usability and control | 10 | Trace cu replay, corectare câmp, respingere dovadă, aprobare în Action Center |

**De ce agent și nu workflow fix:** pentru același tip de daună, următorul pas depinde de ce s-a găsit.

## Research (rezumat)

1. **Dosar la 3 săptămâni după eveniment:** nu e problemă — agenții interoghează data evenimentului (ERA5 din 1940, GFM arhivă din 2015, fereastra [eveniment − 2 zile, + 7 zile]). Întârzierea intră doar în F5.
2. **Cifre:** ~10% fraudă (estimare Insurance Europe); PAD 2024: 1.165 dosare, 39 de zile instrumentare medie; Galați sept. 2024: 6.000–7.000 case afectate, 438 dosare PAD.
3. **Soluții existente:** Shift Technology, FRISS/Verisk/SAS, Nearmap/EagleView, Copernicus EMS. Poziționare: înlocuim cele 40 de minute de research manual, nu un tool antifraudă.
4. **Juridic:** GDPR art. 22 (AI doar recomandă, override-urile se înregistrează, nimic nu se respinge automat); AI Act Anexa III 5(c) nu acoperă asigurările de proprietăți; licențe: Open-Meteo gratuit doar necomercial, Copernicus cu atribuire, Street View — verificați termenii.
5. **Date disponibile:** suficiente pentru MVP, gratuite sau cu tier gratuit.
6. **Comunicare între asigurători:** MVP doar intern (hash perceptual, adresă, telefon ca semnale); roadmap: hash-uri de imagini false + amprente de evenimente; registru de persoane doar printr-un organism al industriei.
7. **Knowledge base per eveniment:** o investigație completă → `EventFootprint`; dosarele următoare primesc verificări ieftine per adresă. Galați: 1 investigație + 438 verificări de câteva secunde.
8. **Restul anului:** alte tipuri de daune, subscriere, poză de referință, expunerea portofoliului, audit retroactiv.
9. **Frauda inteligentă:** proximitate (DEM + incertitudine SAR ±20–30 m), daună preexistentă, risc greșit, poliță de ultim moment, poze reciclate, poze editate AI, umflarea pagubei.

### Scenariul de demo „2 m”

1. Runda 1: GFM arată inundație la 150 m, meteo confirmă 140 mm în 48 h, știrile confirmă cartierul → provizoriu „probabil”.
2. Judge-ul vede tensiunea: casa e în afara poligonului, dar dosarul declară „apă în casă, 60 cm”. Re-trimite Zone de risc și Foto-forensic.
3. Runda 2: casa e cu 6 m deasupra marginii apei, două poze au EXIF din martie → „improbabil”, trimitere la antifraudă cu toate dovezile.

## Plan până sâmbătă la 14:00

Ancorăm demo-ul pe inundația din Galați din 14.09.2024 (CEMS EMSR758, GFM, ERA5). Dosarele și persoanele sunt sintetice.

| Interval | Livrabil | Rol |
| --- | --- | --- |
| Vin 22:00–23:00 | Scope înghețat, entitățile Data Fabric, cele 2 dosare de demo, rolurile | Toți |
| Vin 23:00 – Sâm 03:00 | IXP pe cerere și poliță, reguli F1; agentul Meteo cap-coadă; evenimente de trace | A: Maestro + IXP, B: agenți |
| Sâm 03:00–08:00 | Satelit / Zone de risc; Foto-forensic minimal (EXIF); bucla Orchestrator/Judge | B: agenți, C: UI |
| Sâm 08:00–11:00 | UI cu timeline, trace, hartă; aprobare în Action Center; set de evaluare cu 10 dosare | C: UI, A: integrare |
| Sâm 11:00–12:30 | 3 rulări cap-coadă fără erori; video de rezervă; README și arhitectura pe GitHub | Toți |
| Sâm 12:30–14:00 | Pitch repetat de 3 ori, Q&A, buffer | D: pitch |

Reguli: fiecare agent funcționează izolat înainte de a fi legat în buclă; răspunsurile API din demo se salvează local (cache); dormim pe ture.

### Pitch (5 minute)

1. 0:00–0:40 — problema (Galați: 438 dosare, 39 de zile; până la 10% fraudă).
2. 0:40–1:30 — soluția; de ce agent.
3. 1:30–4:00 — demo: cazul 1 fast-track; cazul 2 „2 m” cu re-dispatch, trace cu replay, decizie în Action Center.
4. 4:00–4:40 — impact: plată mai rapidă, KB per eveniment, cele 360 de zile.
5. 4:40–5:00 — „AI-ul investighează, omul decide.”
