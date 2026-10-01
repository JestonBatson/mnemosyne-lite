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

The domain suite runs without infrastructure. PostgreSQL integration tests run
only when `DATABASE_URL` is set; CI provisions PostgreSQL 16, applies the SQL
migrations to an empty database, and then runs both suites. Schema changes are
migration-owned; the repository does not create tables at runtime.

## HTTP API

### Run with Docker Compose

Copy `.env.example` to `.env`, replace the development password and the matching
password in `DATABASE_URL`, then run:

```sh
docker compose up --build -d --wait
```

Open `http://localhost:8000/docs`. Compose waits for PostgreSQL 16 to become
healthy, runs the explicit one-shot `migrate` service, then starts the API.
The API runs as a non-root user; its container healthcheck calls `/ready`.
PostgreSQL data lives in a named volume and survives API restarts.
The API port binds to localhost and PostgreSQL has no published host port.
The image build context includes only runtime source, migration files, and
package metadata; `.env`, tests, Git history, and local artifacts are excluded.

`docker compose down` stops the stack and preserves its data volume.
`docker compose down --volumes` additionally deletes the development database.

CI builds and boots a fresh Compose stack, runs the canonical flow through real
HTTP, checks the terminal-state `409`, restarts the API, verifies preserved
current state, lineage, provenance, and history, and removes the test volume.
Docker is unavailable on the author's current local machine; the Compose
checkpoint is verified independently in GitHub Actions.

### Run directly with Python

Set `DATABASE_URL` to your PostgreSQL connection URL, then run:

```sh
python scripts/migrate.py
uvicorn mnemosyne_lite.api:app_factory --factory
```

Open `http://localhost:8000/docs` for the interactive OpenAPI contract.
The HTTP layer calls an application service through a repository interface;
lifecycle checks and row locking remain in the storage/domain layer.

| Endpoint | Behavior |
| --- | --- |
| POST /v1/evidence | Create or deduplicate evidence (201) |
| POST /v1/memories | Create an evidence-backed memory (201) |
| GET /v1/memories?subject=service&predicate=port | List active independent claims |
| GET /v1/memories/{id} | Retrieve any version, including terminal records |
| GET /v1/memories/{id}/history | Retrieve full lineage with evidence IDs and revision reasons |
| POST /v1/memories/{id}/revisions | Explicitly supersede an active record (201) |
| POST /v1/memories/{id}/retraction | Retract while preserving history (200) |
| GET /health | Process alive |
| GET /ready | PostgreSQL reachable (200), or unavailable (503) |

Validation errors return 422; missing records return 404; terminal-state
operations and concurrent revision losers return 409. Unexpected failures
return a generic 500 response; database exception details stay server-side.
Evidence deduplication returns the original identity and source attribution.

Authentication and tenant isolation are intentionally outside the project
scope. Mnemosyne Lite demonstrates memory provenance, lifecycle, lineage,
and persistence semantics. Run it in a trusted development environment.

CI also runs a complete HTTP scenario against PostgreSQL:
`8080 OBSERVED → 9000 VERIFIED → 9443 VERIFIED`, checking supersession,
separate provenance, revision reasons, current retrieval, and retraction.
