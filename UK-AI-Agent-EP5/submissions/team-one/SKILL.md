---
name: develop-memory-governance
description: Develop the BasedAI "Enterprise Memory Governance at Scale" hackathon project (permission-aware shared agent memory). Use when working on the team-one submission — building features, fixing bugs, writing tests, or reviewing the bouncer/audit/lineage code. Encodes the project's absolute security rules, architecture, conventions, and working style.
---

# Developing: Enterprise Memory Governance at Scale (team-one)

You are developing a hackathon submission for the **BasedAI track**: a permission-aware layer
over ONE shared memory used by many AI agents, so each user retrieves only the memory items
their role allows. Project lives in
`UK-AI-Agent-EP5/submissions/team-one/` inside a private repo (a copy of `BasedAICo/hackathons`).

## The 4 absolute rules — never violate these

1. **Strict exact-match enforcement, fail-CLOSED.** The read-time access decision matches the
   category tag EXACTLY (case- and whitespace-sensitive). NEVER normalize, interpret, fuzzy-match,
   or LLM-guess at read time. Any mismatch / unknown tag / wrong type / internal error => DENY.
   Failing OPEN (accidentally ALLOW) is the worst possible bug. The decision function must be
   TOTAL (handle any input without raising). Enforce input types — reject non-set allowed-lists
   and non-string categories, because Python's `in` silently degrades to substring/sequence match.

2. **No LLM in the access decision.** A model may classify/label content at WRITE time only
   (and should reuse a canonical tag vocabulary to avoid duplicate tags). The read path is pure
   deterministic code. This is required by the track spec: "enforcement must be deterministic."

3. **The audit log is a legal record, not a demo artifact.** It must be COMPLETE (every ALLOW and
   DENY logged, 100% coverage — there is NO concept of a "sample" or trimmed audit log), append-
   only, UTC-timestamped (high-resolution), tamper-evident (sequence number + SHA-256 hash chain),
   and retained. A logging failure must FAIL CLOSED (refuse access; raise `AuditError`). If log
   growth/retention ever becomes a real concern, PROPOSE the trade-off to the user — never silently
   trim or delete records. Defang spreadsheet formula injection (values starting with `= + - @`).

4. **Enforcement and its logging live at the RETRIEVAL layer**, inside the access decision point —
   not in an application/API layer above it.

## Architecture & current state

- `bouncer.py` — the deterministic "bouncer":
  - `MemoryItem(id, category, text)`, `Decision(item, allowed, reason)`
  - `check_item(allowed_categories, item)` — the single security chokepoint; defensive/total/fail-closed.
  - `filter_allowed(allowed, items)` — pure, no side effects (easy to unit-test).
  - `retrieve(user, allowed, items, log_path=...)` — the AUDITED access path; logs every decision,
    fails closed on audit failure. Real callers use this.
- `audit.py` — tamper-evident audit log:
  - `log_decision(...)` appends one row (`seq, timestamp, user, item_id, category, decision, reason,
    row_hash`), flushes + fsyncs for durability.
  - `verify(path)` recomputes the hash chain; returns `(ok, message)` naming the first broken row.
  - `read_log`, `AuditError`, `_defang`, `_compute_row_hash`.
- `memory.py` — load-time resolvers (DONE): `load_config`/`allowed_categories_for_user` (roles→set,
  deny beats allow, `*` wildcard) + `load_lineage`/`revoked_closure`/`revoked_ids` (lineage graph →
  full transitive revoked set). All fail-closed via `ConfigError`.
- `users.json` (roles→allow/deny categories, users→roles) and `lineage.json` (`derived_from` +
  `revoked`). NOTE: built as JSON, not the `users.yaml` originally sketched (stdlib, no dep).
- `test_bouncer.py` — the test suite (currently **52 tests**). Every fix gets a regression test here.
- `ToDo_audit-log.md` — audit roadmap. Deferred upside: blockchain anchoring (Kaspa — anchor only
  the chain hash, never raw records), retention segmentation, extra fields (`event_type`,
  `user_location`/`item_jurisdiction` for the cross-border bonus).
- In-repo docs: `HANDOFF.md` (start-here orientation + OS-agnostic run steps), `TODO.md` (master
  backlog), `FEATURES.md`, `REVIEW_PROMPT.md`, `NAMING_AND_TRADEMARK_NOTES.md`, `ToDo_audit-log.md`.
  Project display name: **GOVhence MEM-Ø** (`MEM-0` when typed). NOTE: this `SKILL.md` is itself
  committed to the repo — to hand off, copy it verbatim into the new machine's skills folder. No
  re-interpretation needed; the file IS the handover.

### Milestone roadmap (build one at a time, verify before the next)
M1 bouncer ✅ · M2 tests ✅ · audit log + tamper-evidence ✅ · M3 users.json + `memory.py` loaders ✅
(roles→allowed; `exec` = allow `*` deny `legal`) · M5 lineage-based revocation ✅ (DERIVED_FROM graph;
revoke a source → propagates to all derivatives; revoked beats allowed) ·
**Next:** M6 one `cli.py` entrypoint (wire loader+bouncer+audit; retire hardcoded demo values) ·
M7 real semantic store + open-weight embeddings via **BasedAPIs** (bouncer still filters results) ·
M8 write-time LLM classification via BasedAPIs (label only, never decide).

## How to run

- The core is **pure Python standard library** (built/tested on Python 3.13; works on 3.11+). The
  only third-party dependency is `pytest`, used for tests only.
- Use `python3` (macOS/Linux) or `python` (Windows). If your PATH lacks a real interpreter, call it
  by its full path on your machine.
- Tests, from the team-one folder: `<python> -m pytest -v` (exit code 0 = all pass).
- Demo: `<python> bouncer.py`  ·  Integrity: `<python> -c "import audit; print(audit.verify())"`
- A virtual environment ("toolbox") can live in `team-one/.venv` (git-ignored). It holds `pytest`.
- Throwaway/probe scripts go in a temp/scratch dir, NOT the project folder; use a TEMP log
  file in tests/probes — never the real `audit_log.csv`.

## Working style (how the user wants you to work)

- **The user is new to coding.** Explain every technical term plainly (what `venv`/`commit`/`suite`
  mean), including inside command descriptions and confirmation prompts. Favour longer, clearer
  summaries over terse ones. Never approve-gate the user on a command full of unexplained jargon.
- **One small step at a time.** Build the smallest testable unit, RUN it, SHOW it working, explain
  it, let the user verify, then stop and check before the next. Don't scaffold the whole stack.
- **Don't batch decision questions.** Answer the user's question first, in prose. Ask design/tooling
  questions one at a time, only when that decision is actually next — not as a wall of multiple-choice.
- **Security-first; propose, don't assume.** On any trade-off, lead with the safe option and a clear
  proposal for the user to choose — never quietly pick convenience over completeness/safety.
- **Ponytail principle.** Least code that genuinely solves it; reuse stdlib and existing functions;
  fix root causes at the single chokepoint, not symptoms scattered around. Flag over-engineering.
- **A fix without a test rots.** Every defect fix gets a regression test in `test_bouncer.py`, and
  you run the full suite (confirm nothing old broke) before declaring done.
- **Verify with evidence, not claims.** Run the code, show real output / exit codes / the actual
  audit log; prove behaviour rather than asserting it.

## Hard constraints (hackathon)

- **Open-weight models only** in the product (Llama/Qwen/Mistral/etc., served via BasedAPIs). No
  closed models in the loop.
- **Never commit secrets.** Use `.env.example` with placeholders; keep real values local. Throwaway
  wallet only if doing the blockchain-anchoring upside.
- The PR (at submission time) must touch ONLY the team folder. Folder names are lowercase-hyphenated.
- Judging weights: autonomy/tech 30% · innovation 25% · use of BasedAI/sponsor tech 20% ·
  real-world usefulness 15% · demo 10%. Deadline: submit before Demo Day (4 Jul 2026).

## Definition of done for any change

1. Code is simple, readable, and explained in plain terms to the user.
2. It honours all 4 absolute rules (no fail-open, no LLM in decision, audit complete+tamper-evident
   +fail-closed, enforcement at retrieval layer).
3. New behaviour has a regression test; the FULL suite passes (exit code 0).
4. You showed the user real evidence it works, and (when asked) committed/pushed to the PRIVATE repo
   after confirming no secrets and that it stayed private.
