"""Test configuration: put the application code (src/) on the import path so tests can
`import bouncer`, `import classifier`, `import llm`, etc. Data lives in ../data and is
resolved by each module relative to its own location."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
