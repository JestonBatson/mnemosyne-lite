CREATE TYPE memory_status AS ENUM ('OBSERVED','INFERRED','VERIFIED','SUPERSEDED','RETRACTED');

CREATE TABLE evidence (
    id UUID PRIMARY KEY,
    content_hash VARCHAR(64) UNIQUE NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    source_reference VARCHAR(512) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE memories (
    id UUID PRIMARY KEY,
    lineage_id UUID NOT NULL,
    subject VARCHAR(128) NOT NULL,
    predicate VARCHAR(128) NOT NULL,
    value TEXT NOT NULL,
    status memory_status NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    supersedes_id UUID REFERENCES memories(id),
    superseded_by_id UUID UNIQUE REFERENCES memories(id),
    created_at TIMESTAMPTZ NOT NULL,
    retracted_at TIMESTAMPTZ
);

CREATE INDEX memories_lineage_id_idx ON memories(lineage_id);
CREATE INDEX memories_subject_predicate_idx ON memories(subject, predicate);

CREATE TABLE memory_provenance (
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE RESTRICT,
    evidence_id UUID NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    relationship VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(memory_id, evidence_id)
);

CREATE TABLE revisions (
    id UUID PRIMARY KEY,
    old_memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE RESTRICT,
    new_memory_id UUID UNIQUE NOT NULL REFERENCES memories(id) ON DELETE RESTRICT,
    reason VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
