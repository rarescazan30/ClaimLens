# demo/

Demo anchored on real events. Claims and people are **synthetic**.

| Case | File | Documents | Meant to show |
| --- | --- | --- | --- |
| C-8001 flood | `cases/flood.json` | `documents/flood/` (the team's PDFs + `poza.png`) | Galați flood 14.09.2024, Pechea; runs through to the agents |
| C-8002 storm | `cases/storm.json` | `documents/storm/` (the team's PDFs + `poza.png`) | Bucharest windstorm 17.07.2025; runs through to the agents |
| C-8003 paused | `cases/paused.json` | `documents/paused/` (generated) + `flood/poza.png` | The flood claim on a policy (P-8003) that expired 31.01.2024: pauses on `policy_active` |

`cases/` holds case files only; documents and photos live together in `documents/`. The team's files in
`documents/flood|storm` are the standard template and are not edited. `documents/paused/` is written from
`cases/sources/C-8003.json` by `backend/scripts/make_documents.py`. All people are synthetic; the team's CNPs fail
the checksum, so every demo claim shows a `cnp_invalid` warning. The backend loads every `cases/*.json` at startup.

## What we measured (use these numbers in the pitch)

| Fact | Value | Source |
| --- | --- | --- |
| Rain near Pechea on 14.09.2024 | 45.7–47.9 mm in 24 h, about 75 mm in 72 h | Open-Meteo reanalysis |
| Flood map | EMSR758, area "Pechea" (AOI03), maximum flood extent 918 ha, radar image of 17.09.2024 | Copernicus CEMS |
| Fraud-case point | 150 m outside the flood extent, about 13 m above its edge | Copernicus DEM (90 m grid) |
| Gusts in Galați on 26.11.2023 | 90.4 km/h (Constanța: 103.7 km/h) | Open-Meteo reanalysis |

Things that are **not** true and must not be said: "140 mm in 48 h" (the data shows about 75 mm in 72 h).

## Limits found while building (worth knowing for Q&A)

- Copernicus mapped only the **Pechea** area for EMSR758. The three other requested areas (Jorăști, Cudalbi,
  Liești) were "not produced because of remote sensing limitations". A house there gets "inconclusive" from the
  satellite agent, never "outside the flood". The fraud house must stay inside lon 27.62–27.87, lat 45.46–45.74.
- Reanalysis weather underestimates short summer storms: the Timișoara storm of 17.09.2017 (over 100 km/h
  measured) shows as 53.6 km/h. Large winter windstorms are captured well, which is why the honest case uses
  26.11.2023.
- OpenStreetMap has almost no buildings mapped around Pechea, so "is there a house here" has to be checked by eye.

Other folders: `cache/` saved API responses (committed, used by replay mode), `mock/` sample API responses
for the frontend, and the backup video goes here too.
