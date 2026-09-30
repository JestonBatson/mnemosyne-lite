import pytest
from uuid import uuid4

from pydantic import ValidationError
from mnemosyne_lite.models import EvidenceCreate, MemoryCreate, MemoryStatus, RevisionCreate
from mnemosyne_lite.service import DomainError, MemoryService


def evidence(service: MemoryService, content: str):
    return service.add_evidence(EvidenceCreate(source_type="config", source_reference="example", content=content))


def test_canonical_supersession_preserves_history():
    service = MemoryService()
    observed = evidence(service, "service port is 8080")
    old = service.create_memory(MemoryCreate(subject="service", predicate="port", value="8080", status="OBSERVED", confidence=.72, evidence_ids=[observed.id]))
    verified = evidence(service, "PORT=9000")
    current = service.revise(old.id, RevisionCreate(value="9000", status="VERIFIED", confidence=.98, evidence_ids=[verified.id], reason="authoritative config"))
    assert service.get_memory(old.id).status == MemoryStatus.SUPERSEDED
    assert service.current("service", "port") == [current]
    assert [item.value for item in service.history(old.id)] == ["8080", "9000"]
    assert service.provenance[old.id] == {observed.id}
    assert service.provenance[current.id] == {verified.id}


def test_memory_requires_existing_provenance():
    with pytest.raises(DomainError):
        MemoryService().create_memory(MemoryCreate(subject="x", predicate="y", value="z", status="OBSERVED", confidence=.5, evidence_ids=[uuid4()]))


def test_retraction_preserves_record_but_hides_current():
    service = MemoryService(); item = evidence(service, "fact")
    memory = service.create_memory(MemoryCreate(subject="x", predicate="y", value="z", status="VERIFIED", confidence=.9, evidence_ids=[item.id]))
    assert service.retract(memory.id).status == MemoryStatus.RETRACTED
    assert service.current("x", "y") == []


def test_duplicate_evidence_is_idempotent():
    service = MemoryService()
    assert evidence(service, "same").id == evidence(service, "same").id


@pytest.mark.parametrize("confidence", [-.01, 1.01])
def test_confidence_is_bounded(confidence):
    with pytest.raises(ValidationError):
        MemoryCreate(subject="x", predicate="y", value="z", status="OBSERVED", confidence=confidence, evidence_ids=[uuid4()])


def test_terminal_memories_fail_closed_for_revise_and_retract():
    service = MemoryService(); first = evidence(service, "8080"); second = evidence(service, "9000")
    old = service.create_memory(MemoryCreate(subject="service", predicate="port", value="8080", status="OBSERVED", confidence=.72, evidence_ids=[first.id]))
    service.revise(old.id, RevisionCreate(value="9000", status="VERIFIED", confidence=.98, evidence_ids=[second.id], reason="new config"))
    with pytest.raises(DomainError): service.revise(old.id, RevisionCreate(value="9443", status="VERIFIED", confidence=.99, evidence_ids=[second.id], reason="invalid"))
    with pytest.raises(DomainError): service.retract(old.id)


def test_retracted_memory_cannot_be_revised_or_retracted_again():
    service = MemoryService(); item = evidence(service, "fact")
    memory = service.create_memory(MemoryCreate(subject="x", predicate="y", value="z", status="OBSERVED", confidence=.5, evidence_ids=[item.id]))
    service.retract(memory.id)
    with pytest.raises(DomainError): service.retract(memory.id)
    with pytest.raises(DomainError): service.revise(memory.id, RevisionCreate(value="new", status="VERIFIED", confidence=.9, evidence_ids=[item.id], reason="invalid"))


def test_three_version_chain_has_one_current_and_deterministic_history():
    service = MemoryService(); a, b, c = (evidence(service, value) for value in ("8080", "9000", "9443"))
    first = service.create_memory(MemoryCreate(subject="service", predicate="port", value="8080", status="OBSERVED", confidence=.72, evidence_ids=[a.id]))
    second = service.revise(first.id, RevisionCreate(value="9000", status="INFERRED", confidence=.81, evidence_ids=[b.id], reason="deployment note"))
    third = service.revise(second.id, RevisionCreate(value="9443", status="VERIFIED", confidence=.99, evidence_ids=[c.id], reason="authoritative config"))
    assert [m.value for m in service.history(first.id)] == ["8080", "9000", "9443"]
    assert service.current("service", "port") == [third]


def test_independent_same_claims_are_not_merged_without_explicit_revision():
    service = MemoryService(); a, b = evidence(service, "a"), evidence(service, "b")
    first = service.create_memory(MemoryCreate(subject="service", predicate="port", value="8080", status="OBSERVED", confidence=.7, evidence_ids=[a.id]))
    second = service.create_memory(MemoryCreate(subject="service", predicate="port", value="9000", status="VERIFIED", confidence=.9, evidence_ids=[b.id]))
    assert service.current("service", "port") == [first, second]
    assert service.history(first.id) == [first]


def test_unrelated_memory_does_not_contaminate_history():
    service = MemoryService(); a, b = evidence(service, "a"), evidence(service, "b")
    primary = service.create_memory(MemoryCreate(subject="service", predicate="port", value="8080", status="OBSERVED", confidence=.7, evidence_ids=[a.id]))
    service.create_memory(MemoryCreate(subject="service", predicate="region", value="us-east", status="VERIFIED", confidence=.9, evidence_ids=[b.id]))
    assert service.history(primary.id) == [primary]


def test_terminal_status_cannot_create_new_memory():
    service = MemoryService(); item = evidence(service, "fact")
    with pytest.raises(DomainError):
        service.create_memory(MemoryCreate(subject="x", predicate="y", value="z", status="SUPERSEDED", confidence=.5, evidence_ids=[item.id]))
