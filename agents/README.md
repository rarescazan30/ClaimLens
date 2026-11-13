# agents/

Specialist agents (Agent Builder in Studio Web, or coded agents). One folder per agent.

| Agent | Question it answers | Data / APIs | Status |
| --- | --- | --- | --- |
| `meteo/` | Did the phenomenon happen at the address, on the date, with enough intensity? | Open-Meteo Historical (ERA5 / ERA5-Land), ANM warnings | **real for the demo** |
| `satellite/` | Was the area actually flooded? | Copernicus GFM, Sentinel-2, CEMS Rapid Mapping (EMSR758) | real (or risk_zones) |
| `risk_zones/` | Is the house plausibly exposed? | OSM, Copernicus DEM, ANAR hazard maps, EGMS | real (or satellite) |
| `photo_forensics/` | Are the photos authentic, recent, from the address? | EXIF, reverse image search, C2PA, vision LLM | minimal (EXIF) |
| `street_view/` | What did the house look like before? | Street View metadata, Mapillary | pre-captured |
| `news/` | Independent local confirmation? | Web search, GDELT, ISU/IGSU | pre-captured |

Rules for every agent:
- One competence, a closed list of tools, a step budget (e.g. max 6 tool calls per round).
- Returns the **standard evidence format** — see [`docs/contracts.md`](../docs/contracts.md).
- API down → retry once → alternative source → `inconclusive` with the gap written out. A gap is never "fraud".
- Works in isolation before being wired into the loop. Cache the API responses used in the demo.
