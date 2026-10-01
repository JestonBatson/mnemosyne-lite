"""Thin versioned HTTP interface. Lifecycle decisions stay below this layer."""
import logging
import os
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .application import EvidenceResponse, MemoryApplication, MemoryResponse, Repository
from .models import EvidenceCreate, MemoryCreate, RevisionCreate
from .service import ConflictError, DomainError, NotFoundError
from .storage import PostgresMemoryRepository

logger = logging.getLogger(__name__)


def create_app(repository: Repository) -> FastAPI:
    app = FastAPI(title="Mnemosyne Lite", version="1.0.0", description="Evidence-backed, versioned memory with explicit lineage. Authentication and tenant isolation are outside v1 scope.")
    service = MemoryApplication(repository)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        status = 404 if isinstance(error, NotFoundError) else 409 if isinstance(error, ConflictError) else 422
        return JSONResponse(status_code=status, content={"detail": str(error)})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        logger.error("request failed", exc_info=error)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health", tags=["Operations"])
    def health():
        return {"status": "alive"}

    @app.get("/ready", tags=["Operations"], responses={503: {"description": "PostgreSQL unavailable"}})
    def ready():
        try:
            service.ready()
        except SQLAlchemyError:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    @app.post("/v1/evidence", response_model=EvidenceResponse, status_code=201, tags=["Evidence"])
    def add_evidence(request: EvidenceCreate):
        return service.add_evidence(request)

    @app.post("/v1/memories", response_model=MemoryResponse, status_code=201, tags=["Memories"])
    def create_memory(request: MemoryCreate):
        return service.create_memory(request)

    @app.get("/v1/memories", response_model=list[MemoryResponse], tags=["Memories"])
    def current(subject: str = Query(min_length=1, max_length=128), predicate: str = Query(min_length=1, max_length=128)):
        return service.current(subject, predicate)

    @app.get("/v1/memories/{memory_id}", response_model=MemoryResponse, tags=["Memories"])
    def get_memory(memory_id: UUID):
        return service.get_memory(memory_id)

    @app.get("/v1/memories/{memory_id}/history", response_model=list[MemoryResponse], tags=["Memories"])
    def history(memory_id: UUID):
        return service.history(memory_id)

    @app.post("/v1/memories/{memory_id}/revisions", response_model=MemoryResponse, status_code=201, tags=["Memories"])
    def revise(memory_id: UUID, request: RevisionCreate):
        return service.revise(memory_id, request)

    @app.post("/v1/memories/{memory_id}/retraction", response_model=MemoryResponse, tags=["Memories"])
    def retract(memory_id: UUID):
        return service.retract(memory_id)

    return app


def app_factory() -> FastAPI:
    """Run with uvicorn mnemosyne_lite.api:app_factory --factory."""
    return create_app(PostgresMemoryRepository(os.environ["DATABASE_URL"]))
