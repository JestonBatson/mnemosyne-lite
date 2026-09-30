"""PostgreSQL persistence; domain rules remain in :mod:`mnemosyne_lite.service`."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, create_engine, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .models import EvidenceCreate, MemoryCreate, MemoryStatus, RevisionCreate
from .service import DomainError, LIFECYCLE_TRANSITIONS


class Base(DeclarativeBase): pass


class EvidenceRow(Base):
    __tablename__ = "evidence"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class MemoryRow(Base):
    __tablename__ = "memories"
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_bounds"),)
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    lineage_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("memories.id"))
    superseded_by_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("memories.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProvenanceRow(Base):
    __tablename__ = "memory_provenance"
    memory_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("memories.id", ondelete="RESTRICT"), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False, default="SUPPORTS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class PostgresMemoryRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None: Base.metadata.create_all(self.engine)

    def add_evidence(self, request: EvidenceCreate) -> EvidenceRow:
        digest = sha256(request.content.encode()).hexdigest()
        with self.sessions.begin() as session:
            existing = session.scalar(select(EvidenceRow).where(EvidenceRow.content_hash == digest))
            if existing: return existing
            row = EvidenceRow(content_hash=digest, source_type=request.source_type, source_reference=request.source_reference, content=request.content)
            session.add(row); session.flush()
            return row

    def create_memory(self, request: MemoryCreate) -> MemoryRow:
        with self.sessions.begin() as session:
            self._require_evidence(session, request.evidence_ids)
            if request.status not in {MemoryStatus.OBSERVED, MemoryStatus.INFERRED, MemoryStatus.VERIFIED}: raise DomainError("new memories must be active")
            row = MemoryRow(lineage_id=uuid4(), subject=request.subject, predicate=request.predicate, value=request.value, status=request.status.value, confidence=request.confidence)
            session.add(row); session.flush(); self._attach(session, row.id, request.evidence_ids); return row

    def revise(self, memory_id: UUID, request: RevisionCreate) -> MemoryRow:
        with self.sessions.begin() as session:
            old = session.scalar(select(MemoryRow).where(MemoryRow.id == memory_id).with_for_update())
            if not old or "revise" not in LIFECYCLE_TRANSITIONS[MemoryStatus(old.status)]: raise DomainError("memory is not revisable")
            self._require_evidence(session, request.evidence_ids)
            row = MemoryRow(lineage_id=old.lineage_id, subject=old.subject, predicate=old.predicate, value=request.value, status=request.status.value, confidence=request.confidence, supersedes_id=old.id)
            session.add(row); session.flush(); self._attach(session, row.id, request.evidence_ids)
            old.status = MemoryStatus.SUPERSEDED.value; old.superseded_by_id = row.id
            return row

    @staticmethod
    def _require_evidence(session: Session, ids: list[UUID]) -> None:
        if len(ids) != len(set(ids)) or session.query(EvidenceRow).filter(EvidenceRow.id.in_(ids)).count() != len(ids): raise DomainError("every operation requires existing, distinct evidence")
    @staticmethod
    def _attach(session: Session, memory_id: UUID, ids: list[UUID]) -> None:
        session.add_all(ProvenanceRow(memory_id=memory_id, evidence_id=item) for item in ids)
