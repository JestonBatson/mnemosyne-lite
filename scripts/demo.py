"""Canonical HTTP demo; requires a running local Compose stack."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from smoke_http import request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="mnemosyne-demo-") as temporary:
        state_file = Path(temporary) / "state.json"
        smoke = [sys.executable, str(root / "scripts/smoke_http.py")]
        options = ["--base-url", args.base_url, "--state", str(state_file)]
        subprocess.run([*smoke, "seed", *options], check=True)
        state = json.loads(state_file.read_text())
        print("\nCurrent memory:", flush=True)
        print(json.dumps(request(args.base_url, "GET", "/v1/memories?" + urlencode({"subject": state["subject"], "predicate": "port"})), indent=2), flush=True)
        print("\nFull history with provenance and revision reasons:", flush=True)
        print(json.dumps(request(args.base_url, "GET", f'/v1/memories/{state["ids"][0]}/history'), indent=2), flush=True)
        print("\nRestarting API container…", flush=True)
        subprocess.run(["docker", "compose", "restart", "api"], cwd=root, check=True)
        subprocess.run([*smoke, "verify", *options], check=True)


if __name__ == "__main__":
    main()
