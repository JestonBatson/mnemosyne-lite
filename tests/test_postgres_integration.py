from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("requires a real PostgreSQL DATABASE_URL", allow_module_level=True)

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from mnemosyne_lite.models import EvidenceCreate, MemoryCreate, MemoryStatus, RevisionCreate
from mnemosyne_lite.service import DomainError
from mnemosyne_lite.storage import PostgresMemoryRepository


@pytest.fixture
def repo() -> PostgresMemoryRepository:
    repository = PostgresMemoryRepository(os.environ["DATABASE_URL"])
    with repository.engine.begin() as connection:
        connection.execute(text("DELETE FROM revisions"))
        connection.execute(text("DELETE FROM memory_provenance"))
        connection.execute(text("DELETE FROM memories"))
        connection.execute(text("DELETE FROM evidence"))
    return repository


def evidence(repo: PostgresMemoryRepository, content: str):
    return repo.add_evidence(EvidenceCreate(source_type="config", source_reference="test", content=content))


def memory(repo: PostgresMemoryRepository, evidence_id, value: str = "8080"):
    return repo.create_memory(MemoryCreate(subject="service", predicate="port", value=value, status=MemoryStatus.OBSERVED, confidence=0.72, evidence_ids=[evidence_id]))


def test_persists_deduplicates_and_enforces_constraints(repo: PostgresMemoryRepository) -> None:
    first = evidence(repo, "PORT=8080")
    assert evidence(repo, "PORT=8080").id == first.id
    with repo.engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO evidence (id, content_hash, source_type, source_reference, content, created_at) VALUES (:id, :hash, 'x', 'x', 'x', now())"), {"id": str(uuid4()), "hash": first.content_hash})
    with repo.engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO memories (id, lineage_id, subject, predicate, value, status, confidence, created_at) VALUES (:id, :lineage, 's', 'p', 'v', 'OBSERVED', 1.1, now())"), {"id": str(uuid4()), "lineage": str(uuid4())})


def test_explicit_lineage_provenance_retraction_and_fresh_history(repo: PostgresMemoryRepository) -> None:
    observed_evidence = evidence(repo, "PORT=8080")
    verified_evidence = evidence(repo, "PORT=9000")
    old = memory(repo, observed_evidence.id)
    independent = memory(repo, observed_evidence.id, "7000")
    current = repo.revise(old.id, RevisionCreate(value="9000", status=MemoryStatus.VERIFIED, confidence=0.98, evidence_ids=[verified_evidence.id], reason="authoritative config"))
    assert [item.id for item in repo.current("service", "port")] == [independent.id, current.id]
    assert [item.id for item in repo.history(current.id)] == [old.id, current.id]
    assert repo.provenance_for(old.id) == [observed_evidence.id]
    assert repo.provenance_for(current.id) == [verified_evidence.id]
    repo.retract(current.id)
    assert [item.id for item in repo.current("service", "port")] == [independent.id]
    assert [item.status for item in PostgresMemoryRepository(os.environ["DATABASE_URL"]).history(old.id)] == ["SUPERSEDED", "RETRACTED"]


def test_missing_provenance_and_failed_revision_roll_back(repo: PostgresMemoryRepository) -> None:
    source = evidence(repo, "PORT=8080")
    old = memory(repo, source.id)
    with pytest.raises(DomainError):
        repo.revise(old.id, RevisionCreate(value="9000", confidence=0.98, evidence_ids=[uuid4()], reason="bad evidence"))
    assert [item.id for item in repo.current("service", "port")] == [old.id]
    failing = PostgresMemoryRepository(os.environ["DATABASE_URL"], revision_failpoint=lambda: (_ for _ in ()).throw(RuntimeError("forced rollback")))
    replacement_evidence = evidence(repo, "PORT=9000")
    with pytest.raises(RuntimeError, match="forced rollback"):
        failing.revise(old.id, RevisionCreate(value="9000", confidence=0.98, evidence_ids=[replacement_evidence.id], reason="test rollback"))
    assert [item.id for item in repo.current("service", "port")] == [old.id]
    assert [item.id for item in repo.history(old.id)] == [old.id]


def test_concurrent_revision_allows_only_one_success(repo: PostgresMemoryRepository) -> None:
    original_evidence = evidence(repo, "PORT=8080")
    replacement_evidence = evidence(repo, "PORT=9000")
    old = memory(repo, original_evidence.id)

    def revise(value: str):
        try:
            return PostgresMemoryRepository(os.environ["DATABASE_URL"]).revise(old.id, RevisionCreate(value=value, confidence=0.98, evidence_ids=[replacement_evidence.id], reason="concurrent test"))
        except DomainError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revise, ["9000", "9443"]))
    assert sum(item is not None for item in results) == 1
    assert len(repo.current("service", "port")) == 1
    assert len(repo.history(old.id)) == 2
