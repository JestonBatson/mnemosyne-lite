# Design decisions and boundaries

## Explicit revisions, independent claims

Same subject and predicate do not imply agreement, contradiction, or shared
identity. Only an explicit revision establishes lineage. Search in v1 means
exact subject/predicate filtering of active claims, not full-text or semantic search.

## Deterministic lifecycle

OBSERVED, INFERRED, and VERIFIED can be revised or retracted. SUPERSEDED and
RETRACTED are terminal. The caller chooses assertion status and confidence;
VERIFIED is not proof that the service verified reality, and confidence is a
bounded metadata value rather than a calibrated probability.

The single status enum is a deliberate v1 compromise. A verified record later
marked SUPERSEDED loses its original assertion label in that row. A future
model could separate assertion status from record lifecycle. The demo shows the
assertion labels at creation; its final history shows the terminal states.

## Provenance and retained history

Evidence content is stored with source metadata and an exact SHA-256 content hash.
Duplicate content returns the first identity and attribution, even when a later
caller supplies different source metadata. There is no provenance signature,
source authenticity check, or tamper-resistant storage. The API offers no update
or delete operation for evidence, but a database administrator can modify it.
Concurrent duplicate evidence creation can hit the unique constraint and return
a generic 500; sequential deduplication is the supported and tested v1 behavior.

Revision inserts a new value and its own provenance, retains the old provenance,
records a reason, and links both records. Retraction retains the same row and
records a retraction timestamp; it does not currently record a retraction reason.

## Concurrency and consistency

PostgreSQL row locking serializes competing revisions or retractions of the same
record. This is validated with separate concurrent transactions and HTTP callers.
Response assembly uses additional reads after commit; compound history responses
are not a single database snapshot during concurrent writes. Retrieval is unpaged,
so large histories and broad claim sets have not been optimized or load-tested.

## Intentional scope

No authentication, tenant isolation, embeddings, semantic contradiction detection,
automatic truth arbitration, model calls, event bus, or cloud deployment in v1.
The project demonstrates backend state semantics, not a finished hosted memory
platform. Dependency versions and base-image tags are not locked to a complete
reproducible bill of materials; CI validates the resolved build at each commit.
