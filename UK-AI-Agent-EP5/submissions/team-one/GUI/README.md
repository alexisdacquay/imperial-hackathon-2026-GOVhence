# GUI — GOVhence MEM-Ø Security Audit Console

A dark, single-screen security-audit console that visualizes the GOVhence MEM-Ø
memory-access pipeline: an animated orchestration diagram (GOVhence routing to
Classifier → Judge → Bouncer → Responder, with the async Memoriser path), a
Bouncer RBAC/ACL allow/deny gate, and an append-only audit log. The Classifier,
Judge, and Responder call a live LLM; the Bouncer is script-only (no LLM).

## Files

- `index.html` — self-contained build. Open directly in any browser, works offline. No dependencies.
- `GOVhence Audit Console.dc.html` — editable source (Design Component).
- `support.js` — runtime required by the source file.

## Run

Just open `index.html` in a browser.
