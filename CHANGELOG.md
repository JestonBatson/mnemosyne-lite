# Release notes

## v1.0.0 — prepared release

- Evidence with source attribution and exact-content deduplication.
- Explicit memory lineage, provenance, confidence, revision reasons, and retraction.
- PostgreSQL migrations, atomic revision/retraction, and concurrency conflict handling.
- Versioned FastAPI endpoints, interactive documentation, health and readiness checks.
- Non-root Docker image, PostgreSQL 16 Compose stack, and persistent volume.
- 25 domain/persistence/API tests and independent Compose HTTP/restart smoke checks.
- Canonical runnable demo, architecture diagrams, design tradeoffs, and sanitation review.

This release targets trusted local demonstration. Authentication, tenant isolation,
semantic retrieval, and public cloud hosting are outside scope.
