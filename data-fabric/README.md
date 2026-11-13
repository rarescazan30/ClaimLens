# data-fabric/

Data Service entities. Define them first — every other part reads or writes them.

| Entity | Holds |
| --- | --- |
| `Claim` | Case ID, policy, damage type, event date, address, stage, score, recommendation, adjuster decision + override reason |
| `Policy` | Holder, address, validity, waiting period, covered risks, sum insured, product (PAD / optional) |
| `Evidence` | One row per agent per round, in the standard evidence format |
| `TraceStep` | One row per trace event — drives the UI timeline and replay |
| `EventFootprint` | Knowledge base per event: flood polygon, meteo maxima, confirmed news, sources, version |
| `WeightConfig` | Score profile per damage type: base prior + weight per agent |

Field details: [`docs/contracts.md`](../docs/contracts.md). Demo data is synthetic.
