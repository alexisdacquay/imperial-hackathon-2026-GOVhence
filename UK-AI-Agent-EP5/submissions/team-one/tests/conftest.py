"""Test configuration: put the application code (src/) on the import path so tests can
`import bouncer`, `import classifier`, `import llm`, etc. Data lives in ../data and is
resolved by each module relative to its own location."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import bouncer  # noqa: E402  (needs the src path above)
import eventlog  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_runtime(tmp_path, monkeypatch):
    """Every test writes its activity events to a TEMP file (never the real
    data/events.jsonl) and starts with a COLD ACL cache, so each test's own
    users.json (unique tmp_path) is read fresh and no cache leaks across tests."""
    monkeypatch.setattr(eventlog, "_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(eventlog, "_seq", None)
    monkeypatch.setattr(eventlog, "_run", None)
    bouncer._reset_acl_cache()
