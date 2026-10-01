"""PostgreSQL repository for the validated Mnemosyne Lite domain model."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, create_engine, select
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import EvidenceCreate, MemoryCreate, MemoryStatus, RevisionCreate
from .service import ACTIVE, ConflictError, DomainError, LIFECYCLE_TRANSITIONS, NotFoundError


class Base(DeclarativeBase):
    """ORM metadata retained for query mapping; migrations own the schema."""


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
    status: Mapped[MemoryStatus] = mapped_column(PG_ENUM(MemoryStatus, name="memory_status", create_type=False), nullable=False)
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


class RevisionRow(Base):
    __tablename__ = "revisions"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    old_memory_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("memories.id", ondelete="RESTRICT"), nullable=False)
    new_memory_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("memories.id", ondelete="RESTRICT"), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class PostgresMemoryRepository:
    def __init__(self, database_url: str, revision_failpoint: Callable[[], None] | None = None):
        self.engine = create_engine(database_url)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self._revision_failpoint = revision_failpoint

    def add_evidence(self, request: EvidenceCreate) -> EvidenceRow:
        digest = sha256(request.content.encode()).hexdigest()
        with self.sessions.begin() as session:
            existing = session.scalar(select(EvidenceRow).where(EvidenceRow.content_hash == digest))
            if existing:
                return existing
            row = EvidenceRow(content_hash=digest, source_type=request.source_type, source_reference=request.source_reference, content=request.content)
            session.add(row)
            session.flush()
            return row

    def create_memory(self, request: MemoryCreate) -> MemoryRow:
        if request.status not in ACTIVE:
            raise DomainError("new memories must be active")
        with self.sessions.begin() as session:
            self._require_evidence(session, request.evidence_ids)
            row = MemoryRow(lineage_id=uuid4(), subject=request.subject, predicate=request.predicate, value=request.value, status=request.status, confidence=request.confidence)
            session.add(row)
            session.flush()
            self._attach(session, row.id, request.evidence_ids)
            return row

    def revise(self, memory_id: UUID, request: RevisionCreate) -> MemoryRow:
        if request.status not in ACTIVE:
            raise DomainError("a revision must create an active memory")
        with self.sessions.begin() as session:
            old = session.scalar(select(MemoryRow).where(MemoryRow.id == memory_id).with_for_update())
            if not old:
                raise NotFoundError("memory not found")
            if "revise" not in LIFECYCLE_TRANSITIONS[old.status]:
                raise ConflictError("memory is not revisable")
            self._require_evidence(session, request.evidence_ids)
            row = MemoryRow(lineage_id=old.lineage_id, subject=old.subject, predicate=old.predicate, value=request.value, status=request.status, confidence=request.confidence, supersedes_id=old.id)
            session.add(row)
            session.flush()
            self._attach(session, row.id, request.evidence_ids)
            session.add(RevisionRow(old_memory_id=old.id, new_memory_id=row.id, reason=request.reason))
            if self._revision_failpoint:
                self._revision_failpoint()
            old.status = MemoryStatus.SUPERSEDED
            old.superseded_by_id = row.id
            return row

    def retract(self, memory_id: UUID) -> MemoryRow:
        with self.sessions.begin() as session:
            row = session.scalar(select(MemoryRow).where(MemoryRow.id == memory_id).with_for_update())
            if not row:
                raise NotFoundError("memory not found")
            if "retract" not in LIFECYCLE_TRANSITIONS[row.status]:
                raise ConflictError("memory is not retractable")
            row.status = MemoryStatus.RETRACTED
            row.retracted_at = datetime.now(UTC)
            return row

    def current(self, subject: str, predicate: str) -> list[MemoryRow]:
        with self.sessions() as session:
            return list(session.scalars(select(MemoryRow).where(MemoryRow.subject == subject, MemoryRow.predicate == predicate, MemoryRow.status.in_(ACTIVE)).order_by(MemoryRow.created_at, MemoryRow.id)))

    def history(self, memory_id: UUID) -> list[MemoryRow]:
        with self.sessions() as session:
            memory = session.get(MemoryRow, memory_id)
            if not memory:
                raise NotFoundError("memory not found")
            return list(session.scalars(select(MemoryRow).where(MemoryRow.lineage_id == memory.lineage_id).order_by(MemoryRow.created_at, MemoryRow.id)))

    def provenance_for(self, memory_id: UUID) -> list[UUID]:
        with self.sessions() as session:
            return list(session.scalars(select(ProvenanceRow.evidence_id).where(ProvenanceRow.memory_id == memory_id).order_by(ProvenanceRow.evidence_id)))

    def get_memory(self, memory_id: UUID) -> MemoryRow:
        with self.sessions() as session:
            row = session.get(MemoryRow, memory_id)
            if row is None:
                raise NotFoundError("memory not found")
            return row

    def revision_for(self, memory_id: UUID) -> RevisionRow | None:
        with self.sessions() as session:
            return session.scalar(select(RevisionRow).where(RevisionRow.new_memory_id == memory_id))

    def ready(self) -> None:
        with self.engine.connect() as connection:
            from sqlalchemy import text
            connection.execute(text("SELECT 1"))

    @staticmethod
    def _require_evidence(session: Session, ids: list[UUID]) -> None:
        if not ids:
            raise DomainError("provenance is required")
        if session.query(EvidenceRow).filter(EvidenceRow.id.in_(set(ids))).count() != len(set(ids)):
            raise NotFoundError("evidence not found")

    @staticmethod
    def _attach(session: Session, memory_id: UUID, ids: list[UUID]) -> None:
        session.add_all(ProvenanceRow(memory_id=memory_id, evidence_id=item) for item in set(ids))
