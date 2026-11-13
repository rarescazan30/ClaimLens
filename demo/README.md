# demo/

Demo anchored on real events. Claims and people are **synthetic**.

| Case | File | Event (real) | Expected outcome |
| --- | --- | --- | --- |
| "Smart fraud" | `cases/fraud.json` (C-1042) | Galați flood, 14.09.2024, Copernicus CEMS EMSR758 | Round 2 re-dispatch → antifraud referral |
| Honest | `cases/honest.json` (C-1038) | Windstorm, 26.11.2023, Galați | Fast-track |

Both files are **drafts**: addresses are placeholders and there are no photos yet. The backend loads every
`cases/*.json` at startup.

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

## To finish the cases

1. Check each address with `python backend/scripts/check_site.py <lat> <lon> <date>`.
2. Fraud photos: metadata stripped; at least one must be a real flood picture already published online
   before 14.09.2024 (otherwise the web copy search correctly finds nothing).
3. Honest photos: real roof damage, EXIF date 26–27.11.2023.
4. Put photos in `cases/photos/<claim id>/` and list them in the case file as `"<claim id>/<file>"`.

Other folders: `cache/` saved API responses (committed, used by replay mode), `mock/` sample API responses
for the frontend, and the backup video goes here too.
