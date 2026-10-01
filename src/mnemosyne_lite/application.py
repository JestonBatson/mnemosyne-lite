"""Application boundary: repository operations and public response models."""
from datetime import datetime
from typing import Protocol, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .models import EvidenceCreate, MemoryCreate, MemoryStatus, RevisionCreate


class Repository(Protocol):
    def add_evidence(self, request: EvidenceCreate) -> Any: ...
    def create_memory(self, request: MemoryCreate) -> Any: ...
    def get_memory(self, memory_id: UUID) -> Any: ...
    def current(self, subject: str, predicate: str) -> list[Any]: ...
    def history(self, memory_id: UUID) -> list[Any]: ...
    def revise(self, memory_id: UUID, request: RevisionCreate) -> Any: ...
    def retract(self, memory_id: UUID) -> Any: ...
    def provenance_for(self, memory_id: UUID) -> list[UUID]: ...
    def revision_for(self, memory_id: UUID) -> Any: ...
    def ready(self) -> None: ...


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    content_hash: str
    source_type: str
    source_reference: str
    content: str
    created_at: datetime


class MemoryResponse(BaseModel):
    id: UUID
    lineage_id: UUID
    subject: str
    predicate: str
    value: str
    status: MemoryStatus
    confidence: float
    created_at: datetime
    supersedes_id: UUID | None
    superseded_by_id: UUID | None
    retracted_at: datetime | None
    evidence_ids: list[UUID]
    revision_reason: str | None


class MemoryApplication:
    def __init__(self, repository: Repository):
        self.repository = repository

    def add_evidence(self, request: EvidenceCreate) -> EvidenceResponse:
        return EvidenceResponse.model_validate(self.repository.add_evidence(request))

    def _response(self, row: Any) -> MemoryResponse:
        revision = self.repository.revision_for(row.id)
        fields = {name: getattr(row, name) for name in MemoryResponse.model_fields if name not in {"evidence_ids", "revision_reason"}}
        return MemoryResponse(**fields, evidence_ids=self.repository.provenance_for(row.id), revision_reason=revision.reason if revision else None)

    def create_memory(self, request: MemoryCreate) -> MemoryResponse:
        return self._response(self.repository.create_memory(request))

    def get_memory(self, memory_id: UUID) -> MemoryResponse:
        return self._response(self.repository.get_memory(memory_id))

    def current(self, subject: str, predicate: str) -> list[MemoryResponse]:
        return [self._response(row) for row in self.repository.current(subject, predicate)]

    def history(self, memory_id: UUID) -> list[MemoryResponse]:
        return [self._response(row) for row in self.repository.history(memory_id)]

    def revise(self, memory_id: UUID, request: RevisionCreate) -> MemoryResponse:
        return self._response(self.repository.revise(memory_id, request))

    def retract(self, memory_id: UUID) -> MemoryResponse:
        return self._response(self.repository.retract(memory_id))

    def ready(self) -> None:
        self.repository.ready()
