# Mnemosyne Lite

Provenance-aware memory infrastructure for AI agents: it records what a system
knows, where it came from, how confident it is, and how beliefs change.

The central demo preserves an observed `port=8080` memory when authoritative
evidence verifies `port=9000`; retrieval returns 9000 while history explains
both claims. Core behavior is deterministic and requires no LLM.

## Lifecycle

`Evidence → Memory → Provenance → Retrieval → Revision → Auditable history`

Statuses: `OBSERVED`, `INFERRED`, `VERIFIED`, `SUPERSEDED`, `RETRACTED`.

| Current status | Revise | Retract |
| --- | --- | --- |
| OBSERVED / INFERRED / VERIFIED | Yes | Yes |
| SUPERSEDED / RETRACTED | No | No |

Equal subject/predicate values are not automatically merged or treated as a
contradiction. Only an explicit revision creates a lineage and supersedes a
prior memory.

## Development

`python -m pip install '.[dev]' && python -m pytest`

The implementation and operational documentation are being completed before
this repository is initialized or published.
