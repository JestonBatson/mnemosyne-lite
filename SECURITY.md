# Security and responsible use

Mnemosyne Lite v1 is a local infrastructure demonstration. Authentication and
tenant isolation are intentionally outside scope. Anyone who can reach the API
can read or mutate memory; use synthetic data and trusted environments only.
Public repository visibility does not imply a publicly deployed service.

Compose binds the API to `127.0.0.1` and does not publish PostgreSQL's port.
Keep those defaults. Before any shared deployment, provide authentication,
authorization, tenant boundaries, request limits, transport security, protected
logs, and a database backup/restore policy appropriate to the environment.
Interactive OpenAPI docs are intentionally enabled for the local demo.

## Existing safeguards

- Pydantic validates request structure, UUIDs, confidence bounds, and selected
  text lengths. Explicit response schemas prevent arbitrary ORM field exposure.
- ORM queries bind parameters. No HTTP route executes shell commands, fetches
  supplied source URLs, accepts files, renders user HTML, or evaluates input.
- Transactional row locks prevent double revision of an active record.
- The database enforces foreign keys, unique evidence hashes, enum values,
  confidence bounds, and supersession references.
- Unexpected errors return generic HTTP 500 responses. Server logs may include
  exception details and SQL parameters; treat logs as potentially sensitive.
- The runtime user is non-root. A build-context allowlist excludes `.env`, Git
  metadata, tests, local caches, and private runtime files.

## Known limits

There is no rate limit, body-size cap, pagination, host allowlist, immutable audit
store, source certification, or cryptographic provenance. Evidence content and
memory values have no maximum text length. Database administrators can bypass
application invariants. Runtime credentials are visible to trusted container
administrators; do not store production credentials in examples or commits.

Use a dedicated disposable database for tests: integration fixtures delete table
contents. The demo writes synthetic records and restarts the local API service.
Stopping Compose preserves its volume; removing volumes permanently deletes its data.

## Reporting

Use the repository's private security advisory reporting option if enabled.
Otherwise open an issue requesting a private reporting channel without including
credentials, private records, or exploit details. This small portfolio project
has no security response SLA. No dependency vulnerability certification is claimed.
