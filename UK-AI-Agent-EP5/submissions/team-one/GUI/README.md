# GUI — GOVhence MEM-Ø Security Audit Console

A dark, single-screen security-audit console that visualizes the GOVhence MEM-Ø
memory-access pipeline. The console is a **pure viewer of the real backend**: it
polls `data/events.jsonl` (written by `src/govhence.py` + `src/bouncer.py` on
every run) and replays each run — the orchestration diagram highlights the active
edge for every real hop, and the logs show the recorded events with their real
millisecond timings. **Bouncer read-access decisions are first-class**: every
per-memory ALLOW/DENY with its reason, permitted/withheld counts, credential
checks against the Profile Store, and the gate's duration in ms.

No LLM calls happen in the browser and no access logic lives here — the GUI
renders what the deterministic backend recorded, nothing more.

## Files

- `GOVhence Audit Console.dc.html` — **the live console** (editable source, Design Component).
- `support.js` — runtime required by the source file.

## Run (live console)

Use the bundled viewer server — `serve_gui.py` — NOT a bare `http.server` on the
project root. It binds to **loopback only** (`127.0.0.1`) and serves **only** the
GUI files and the events feed, so it can never expose `.env` (your live API keys)
or `data/cocoshamem.json` (the ungated memory store) to the network. A plain
`python -m http.server` from `team-one/` would serve the whole directory to every
device on the Wi-Fi — do not do that.

From `team-one/` (`<python>` = `python3` on macOS/Linux, `python` on Windows, or
your venv interpreter: `.venv/bin/python` / `.venv\Scripts\python.exe`):

```
<python> GUI/serve_gui.py            # http://127.0.0.1:8777  (loopback only)
```

then open <http://127.0.0.1:8777/GUI/GOVhence%20Audit%20Console.dc.html>
(http is required — the console fetches `../data/events.jsonl`; needs internet
once for the React/Babel CDN used by `support.js`).

Drive the pipeline from another terminal and watch runs appear live:

```
<python> src/govhence.py ben-driver "where is the visitor parking?"
<python> src/live_test.py             # or the interactive console
```

The header's allow/deny counters are cumulative across the whole events file;
"Replay last run" re-animates the most recent run. On a fresh clone `events.jsonl`
does not exist until the first run — the console shows "no runs yet" until then.
