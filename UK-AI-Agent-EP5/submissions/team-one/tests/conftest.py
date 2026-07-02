"""Test configuration: put the application code (src/) on the import path so tests can
`import bouncer`, `import classifier`, `import llm`, etc. Data lives in ../data and is
resolved by each module relative to its own location."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import eventlog  # noqa: E402  (needs the src path above)


@pytest.fixture(autouse=True)
def _isolate_eventlog(tmp_path, monkeypatch):
    """Every test writes its activity events to a TEMP file, never the real
    data/events.jsonl (project rule: tests never touch runtime artifacts)."""
    monkeypatch.setattr(eventlog, "_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(eventlog, "_seq", None)
    monkeypatch.setattr(eventlog, "_run", None)
