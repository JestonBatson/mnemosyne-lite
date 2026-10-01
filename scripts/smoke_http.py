"""Exercise the deployed service using HTTP only, before and after restart."""
import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


def request(base, method, path, payload=None, expected=200):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        response = urlopen(req, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        if response.status != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, received {response.status}: {body!r}")
        return json.loads(body)


def wait_ready(base):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            request(base, "GET", "/ready")
            request(base, "GET", "/health")
            print("health and database readiness: PASS", flush=True)
            return
        except (OSError, URLError, AssertionError):
            time.sleep(1)
    raise RuntimeError("API did not become ready within 90 seconds")


def verify(base, state):
    current = request(base, "GET", "/v1/memories?" + urlencode({"subject": state["subject"], "predicate": "port"}))
    assert len(current) == 1 and current[0]["id"] == state["ids"][-1]
    assert current[0]["value"] == "9443" and current[0]["status"] == "VERIFIED"
    history = request(base, "GET", f'/v1/memories/{state["ids"][0]}/history')
    assert [row["id"] for row in history] == state["ids"]
    assert [row["value"] for row in history] == ["8080", "9000", "9443"]
    assert [row["status"] for row in history] == ["SUPERSEDED", "SUPERSEDED", "VERIFIED"]
    assert [row["evidence_ids"] for row in history] == [[item] for item in state["evidence_ids"]]
    assert len({row["lineage_id"] for row in history}) == 1
    assert history[1]["revision_reason"] == "config verifies 9000"
    assert history[2]["revision_reason"] == "config verifies 9443"
    assert history[0]["superseded_by_id"] == state["ids"][1]
    assert history[2]["supersedes_id"] == state["ids"][1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["seed", "verify"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    wait_ready(args.base_url)
    if args.phase == "verify":
        verify(args.base_url, json.loads(args.state.read_text()))
        print("restart persistence (current, lineage, provenance, history): PASS")
        return
    state = {"subject": f"smoke-{uuid4()}", "ids": [], "evidence_ids": []}
    for port in [8080, 9000, 9443]:
        evidence = request(args.base_url, "POST", "/v1/evidence", {"source_type": "config", "source_reference": state["subject"], "content": f'{state["subject"]}:PORT={port}'}, expected=201)
        state["evidence_ids"].append(evidence["id"])
        payload = {"value": str(port), "status": "OBSERVED" if port == 8080 else "VERIFIED", "confidence": 0.72 if port == 8080 else 0.98, "evidence_ids": [evidence["id"]]}
        if port == 8080:
            payload.update(subject=state["subject"], predicate="port")
            path = "/v1/memories"
        else:
            payload["reason"] = f"config verifies {port}"
            path = f'/v1/memories/{state["ids"][-1]}/revisions'
        memory = request(args.base_url, "POST", path, payload, expected=201)
        state["ids"].append(memory["id"])
    verify(args.base_url, state)
    print("canonical HTTP flow and provenance/history: PASS", flush=True)
    request(args.base_url, "POST", f'/v1/memories/{state["ids"][0]}/revisions', payload, expected=409)
    print("terminal-state revision returns 409: PASS", flush=True)
    args.state.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
