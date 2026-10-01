import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from mnemosyne_lite.api import create_app
from mnemosyne_lite.service import ConflictError, DomainError, NotFoundError
from mnemosyne_lite.storage import PostgresMemoryRepository


@pytest.fixture
def contract():
    repository = Mock()
    return TestClient(create_app(repository), raise_server_exceptions=False), repository


@pytest.mark.parametrize("error,status", [(NotFoundError("memory not found"), 404), (ConflictError("memory is not revisable"), 409), (DomainError("invalid transition"), 422), (OperationalError("private SQL", {}, Exception("secret")), 500)])
def test_error_contract(contract, error, status):
    client, repository = contract
    repository.get_memory.side_effect = error
    response = client.get(f"/v1/memories/{uuid4()}")
    assert response.status_code == status
    assert "secret" not in response.text
    assert "private SQL" not in response.text


def test_health_readiness_and_openapi(contract):
    client, repository = contract
    assert client.get("/health").json() == {"status": "alive"}
    repository.ready.assert_not_called()
    assert client.get("/ready").status_code == 200
    repository.ready.side_effect = OperationalError("private", {}, Exception())
    assert client.get("/ready").status_code == 503
    assert client.get("/docs").status_code == 200
    assert "/v1/memories/{memory_id}/history" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_schema_validation(contract, confidence):
    client, repository = contract
    response = client.post("/v1/memories", json={"subject": "service", "predicate": "port", "value": "8080", "status": "OBSERVED", "confidence": confidence, "evidence_ids": [str(uuid4())]})
    assert response.status_code == 422
    repository.create_memory.assert_not_called()
    assert client.post("/v1/memories", json={}).status_code == 422
    assert client.get("/v1/memories/not-a-uuid").status_code == 422


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires real PostgreSQL")
def test_http_canonical_three_version_flow():
    repository = PostgresMemoryRepository(os.environ["DATABASE_URL"])
    client = TestClient(create_app(repository))
    subject = f"service-{uuid4()}"

    def evidence(port):
        payload = {"source_type": "config", "source_reference": subject, "content": f"{subject}:PORT={port}"}
        response = client.post("/v1/evidence", json=payload)
        assert response.status_code == 201
        assert client.post("/v1/evidence", json=payload).json()["id"] == response.json()["id"]
        return response.json()["id"]

    first_evidence = evidence(8080)
    payload = {"subject": subject, "predicate": "port", "value": "8080", "status": "OBSERVED", "confidence": 0.72, "evidence_ids": [first_evidence]}
    assert client.post("/v1/memories", json={**payload, "evidence_ids": [str(uuid4())]}).status_code == 404
    assert client.post("/v1/memories", json={**payload, "evidence_ids": []}).status_code == 422
    first = client.post("/v1/memories", json=payload)
    assert first.status_code == 201
    ids = [first.json()["id"]]
    evidence_ids = [first_evidence]
    for port in [9000, 9443]:
        evidence_ids.append(evidence(port))
        revision = {"value": str(port), "status": "VERIFIED", "confidence": 0.98, "evidence_ids": [evidence_ids[-1]], "reason": f"config verifies {port}"}
        response = client.post(f"/v1/memories/{ids[-1]}/revisions", json=revision)
        assert response.status_code == 201
        ids.append(response.json()["id"])
    assert client.get(f"/v1/memories/{ids[0]}").json()["status"] == "SUPERSEDED"
    assert client.get(f"/v1/memories/{ids[-1]}").json()["value"] == "9443"
    history = client.get(f"/v1/memories/{ids[0]}/history").json()
    assert [row["value"] for row in history] == ["8080", "9000", "9443"]
    assert [row["evidence_ids"] for row in history] == [[item] for item in evidence_ids]
    assert history[1]["revision_reason"] == "config verifies 9000"
    assert len({row["lineage_id"] for row in history}) == 1
    assert client.post(f"/v1/memories/{ids[0]}/retraction").status_code == 409
    assert client.post(f"/v1/memories/{ids[0]}/revisions", json=revision).status_code == 409
    params = {"subject": subject, "predicate": "port"}
    assert [row["id"] for row in client.get("/v1/memories", params=params).json()] == [ids[-1]]
    assert client.post(f"/v1/memories/{ids[-1]}/retraction").status_code == 200
    assert client.post(f"/v1/memories/{ids[-1]}/retraction").status_code == 409
    assert client.get("/v1/memories", params=params).json() == []
    assert len(client.get(f"/v1/memories/{ids[0]}/history").json()) == 3
    for suffix in ["", "/history"]:
        assert client.get(f"/v1/memories/{uuid4()}{suffix}").status_code == 404
    assert client.post(f"/v1/memories/{uuid4()}/retraction").status_code == 404
    assert client.post(f"/v1/memories/{uuid4()}/revisions", json=revision).status_code == 404
    assert client.get("/ready").status_code == 200
    repository.engine.dispose()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires real PostgreSQL")
def test_http_concurrent_revision_returns_conflict():
    repository = PostgresMemoryRepository(os.environ["DATABASE_URL"])
    client = TestClient(create_app(repository))
    subject = f"race-{uuid4()}"
    evidence = client.post("/v1/evidence", json={"source_type": "config", "source_reference": subject, "content": subject}).json()["id"]
    memory = client.post("/v1/memories", json={"subject": subject, "predicate": "port", "value": "8080", "status": "OBSERVED", "confidence": 0.72, "evidence_ids": [evidence]}).json()["id"]
    barrier = Barrier(2)

    def revise(port):
        with TestClient(create_app(repository)) as caller:
            barrier.wait(timeout=10)
            return caller.post(f"/v1/memories/{memory}/revisions", json={"value": port, "status": "VERIFIED", "confidence": 0.98, "evidence_ids": [evidence], "reason": "concurrent request"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(revise, ["9000", "9443"])) == [201, 409]
    assert len(client.get(f"/v1/memories/{memory}/history").json()) == 2
    repository.engine.dispose()
