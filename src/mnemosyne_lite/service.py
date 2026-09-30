from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from .models import Evidence, EvidenceCreate, Memory, MemoryCreate, MemoryStatus, RevisionCreate


class DomainError(ValueError):
    """Raised when an operation would violate the memory lifecycle."""


ACTIVE = {MemoryStatus.OBSERVED, MemoryStatus.INFERRED, MemoryStatus.VERIFIED}
LIFECYCLE_TRANSITIONS = {
    MemoryStatus.OBSERVED: {"revise", "retract"},
    MemoryStatus.INFERRED: {"revise", "retract"},
    MemoryStatus.VERIFIED: {"revise", "retract"},
    MemoryStatus.SUPERSEDED: set(),
    MemoryStatus.RETRACTED: set(),
}


@dataclass
class Revision:
    old_memory_id: UUID
    new_memory_id: UUID
    reason: str
    created_at: datetime


@dataclass
class MemoryService:
    evidence: dict[UUID, Evidence] = field(default_factory=dict)
    evidence_by_hash: dict[str, UUID] = field(default_factory=dict)
    memories: dict[UUID, Memory] = field(default_factory=dict)
    provenance: dict[UUID, set[UUID]] = field(default_factory=dict)
    revisions: list[Revision] = field(default_factory=list)

    def add_evidence(self, request: EvidenceCreate) -> Evidence:
        digest = sha256(request.content.encode()).hexdigest()
        if existing := self.evidence_by_hash.get(digest):
            return self.evidence[existing]
        record = Evidence(source_type=request.source_type, source_reference=request.source_reference, content_hash=digest, created_at=datetime.now(UTC))
        self.evidence[record.id] = record
        self.evidence_by_hash[digest] = record.id
        return record

    def create_memory(self, request: MemoryCreate) -> Memory:
        self._require_evidence(request.evidence_ids)
        if request.status not in ACTIVE:
            raise DomainError("new memories must begin in an active lifecycle state")
        record = Memory(subject=request.subject, predicate=request.predicate, value=request.value, status=request.status, confidence=request.confidence, created_at=datetime.now(UTC))
        self.memories[record.id] = record
        self.provenance[record.id] = set(request.evidence_ids)
        return record

    def revise(self, memory_id: UUID, request: RevisionCreate) -> Memory:
        old = self.get_memory(memory_id)
        if "revise" not in LIFECYCLE_TRANSITIONS[old.status]:
            raise DomainError("only active memories can be revised")
        self._require_evidence(request.evidence_ids)
        if request.status not in ACTIVE:
            raise DomainError("a revision must create an active memory")
        new = Memory(subject=old.subject, predicate=old.predicate, value=request.value, status=request.status, confidence=request.confidence, created_at=datetime.now(UTC))
        self.memories[new.id] = new
        self.provenance[new.id] = set(request.evidence_ids)
        self.memories[old.id] = old.model_copy(update={"status": MemoryStatus.SUPERSEDED, "superseded_by": new.id})
        self.revisions.append(Revision(old.id, new.id, request.reason, datetime.now(UTC)))
        return new

    def retract(self, memory_id: UUID) -> Memory:
        memory = self.get_memory(memory_id)
        if "retract" not in LIFECYCLE_TRANSITIONS[memory.status]:
            raise DomainError("only active memories can be retracted")
        revised = memory.model_copy(update={"status": MemoryStatus.RETRACTED})
        self.memories[memory_id] = revised
        return revised

    def get_memory(self, memory_id: UUID) -> Memory:
        try:
            return self.memories[memory_id]
        except KeyError as error:
            raise DomainError("memory not found") from error

    def current(self, subject: str, predicate: str) -> list[Memory]:
        return [m for m in self.memories.values() if m.subject == subject and m.predicate == predicate and m.status in ACTIVE]

    def history(self, memory_id: UUID) -> list[Memory]:
        root = self.get_memory(memory_id)
        chain = [root]
        while chain[-1].superseded_by:
            chain.append(self.get_memory(chain[-1].superseded_by))
        return chain

    def _require_evidence(self, evidence_ids: list[UUID]) -> None:
        if not evidence_ids or any(item not in self.evidence for item in evidence_ids):
            raise DomainError("every memory operation requires existing evidence")
