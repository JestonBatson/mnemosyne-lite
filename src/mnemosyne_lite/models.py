from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MemoryStatus(StrEnum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    VERIFIED = "VERIFIED"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"


class EvidenceCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=64)
    source_reference: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1)


class MemoryCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=128)
    predicate: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1)
    status: MemoryStatus
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[UUID] = Field(min_length=1)


class RevisionCreate(BaseModel):
    value: str = Field(min_length=1)
    status: MemoryStatus = MemoryStatus.VERIFIED
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[UUID] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=512)


class Evidence(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_type: str
    source_reference: str
    content_hash: str
    created_at: datetime


class Memory(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    subject: str
    predicate: str
    value: str
    status: MemoryStatus
    confidence: float
    created_at: datetime
    superseded_by: UUID | None = None
