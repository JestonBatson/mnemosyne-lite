"""CI inspection of project files in the built image; run via Python stdin."""
import os
from pathlib import Path

assert os.getuid() != 0, "runtime must not be root"
root = Path("/app")
for path in root.rglob("*"):
    assert path.name not in {".git", ".env", ".env.example", "tests", "__pycache__", ".pytest_cache", "build"}, f"unexpected image artifact: {path}"
    assert not path.name.endswith((".db", ".sqlite", ".sqlite3", ".log", ".egg-info")), f"unexpected image artifact: {path}"
    if path.is_file():
        content = path.read_bytes()
        assert b"/Users/" not in content, f"local path in image: {path}"
        assert b"BEGIN OPENSSH PRIVATE KEY" not in content, f"private key in image: {path}"
for key in ["DATABASE_URL", "POSTGRES_PASSWORD", "GITHUB_TOKEN", "OPENAI_API_KEY"]:
    assert key not in os.environ, f"credential baked into image environment: {key}"
assert (root / "scripts/migrate.py").is_file()
assert (root / "migrations/001_initial.sql").is_file()
print("non-root runtime and project image contents: PASS")
