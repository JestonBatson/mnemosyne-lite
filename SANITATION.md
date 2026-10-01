# Release sanitation review

Reviewed 2026-10-01 for the prepared v1 release. This is a source/configuration
review plus targeted pattern scanning, not a guarantee that every possible secret
format or dependency vulnerability has been detected.

## Scope and results

- Inspected tracked filenames, source, fixtures, runtime configuration, and all
  four pre-release commits (`a615255`, `5b84985`, `6a3477f`, `51e3672`).
- Targeted history scans found no recognizable GitHub/OpenAI/AWS credential
  patterns, private keys, private monorepo references, or personal workspace paths.
- Database URL matches were reviewed: examples contain clearly disposable local
  credentials; CI uses a disposable service password or randomly generated and
  masked Compose credentials. No production database endpoint was found.
- Synthetic fixture content is limited to example service/port claims. No raw
  conversation, personal memory exports, runtime database, log, or real `.env`
  is tracked. The release review scripts contain pattern strings, not private data.
- Git authorship uses the intended public professional name and GitHub noreply
  address. The MIT license intentionally identifies the author.
- Docker uses an allowlisted build context. CI inspects the built image's project
  files for environment files, Git metadata, tests, caches, database/log files,
  local paths, and private keys; it also checks non-root execution and that
  credentials are absent from the default image environment.

The image check covers project files under `/app` and selected environment keys,
not a complete audit of base-image contents, every image layer, or installed
third-party packages. README and package metadata are intentionally included;
architecture/security documents and demo/test scripts are excluded from the image.

## Security findings

No critical or high-severity issue was identified within the intended trusted
local demonstration boundary. The following documented limitations remain.

### S1 — Authentication absent (shared deployment risk)

Rule: FASTAPI-AUTH-001 / FASTAPI-AUTHZ-001. Severity: High **if exposed to untrusted
users**, accepted outside v1 scope. Evidence: `src/mnemosyne_lite/api.py:44–70`
has no authentication dependency; `docker-compose.yml` binds API access to loopback.
Any reachable caller can read or change records. Keep the local boundary; add
authentication, authorization, and tenant isolation before shared hosting.

### S2 — Resource limits absent

Rule: FASTAPI-LIMITS-001. Severity: Low within the local boundary. Evidence:
`src/mnemosyne_lite/models.py:21,27,34` accepts unbounded content/value strings;
`src/mnemosyne_lite/storage.py:124–133` returns unpaged current/history results.
Large requests or histories can exhaust resources. Trusted synthetic workloads
are the current mitigation; future deployment needs quotas, size limits, and pagination.

### S3 — Exception logs may contain submitted values

Rule: sensitive-data minimization. Severity: Low within the local boundary.
Evidence: `src/mnemosyne_lite/api.py:29` logs exception details; database exceptions
can include SQL parameters. HTTP clients receive a generic 500. Protect logs,
use synthetic data, and apply structured redaction before handling private records.

### S4 — Dependency resolution is not fully pinned

Rule: FASTAPI-SUPPLY-001. Severity: Low. Evidence: `pyproject.toml:10` uses minimum
version requirements and Docker uses mutable Python/PostgreSQL tags. CI validates
each resolved build, but exact rebuilds and advisory status are not guaranteed.
Add a maintained lockfile, dependency review, and image digest policy for a
long-lived deployment. This release makes no dependency vulnerability certification.

OpenAPI exposure is intentional for the local demo. No cookie sessions, custom
user HTML rendering, file-serving routes, outbound source URL fetches, or request
shell execution were found. ORM queries use bound values. These observations do
not certify that the service is suitable for untrusted production use.
