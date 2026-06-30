---
name: develop-memory-governance
description: Develop the BasedAI "Enterprise Memory Governance at Scale" hackathon project (permission-aware shared agent memory). Use when working on the team-one submission — building features, fixing bugs, writing tests, or reviewing the bouncer/audit/lineage code. Points to the 3 authoritative spec sources (the authority), then our current architecture, conventions, and working style. The spec — not this file — is the source of truth.
---

# Developing: Enterprise Memory Governance at Scale (team-one)

Hackathon submission for the **BasedAI track**. Project lives in
`UK-AI-Agent-EP5/submissions/team-one/` (a fork of `BasedAICo/hackathons`).

## ⚠️ THE SPEC IS THE AUTHORITY — read the sources, do not trust this file's gloss

The requirements live in the three sources below, NOT in this SKILL. Earlier versions of this file
paraphrased and INVENTED requirements (e.g. "exact-match", "category tag", "case-sensitive") that the
spec never states. Those were design choices, not requirements. **Load the sources and quote them;
treat anything in this file beyond the verbatim quotes as our changeable design, not the spec.**

### The 3 authoritative sources
1. **Canonical requirements doc (most detailed):**
   <https://docs.google.com/document/d/1sj3DdGClW9Ft-hOOmTgcHK4uumn5wrXlA6oU3nMNmMc/edit>
   — full track requirements: objective, access-control/determinism rules, ACL sync, derived-memory
   governance, audit, model constraints, latency, bonus challenges, deadline. *Fetch via
   `…/export?format=txt` then follow the redirect, if the editor URL won't render.*
2. **BasedAI event page:**
   <https://basedai.co/events/hackathon-UK-AI-AGENT-EP5>
   — same track requirements in event-page form, plus event logistics.
3. **Repo brief + process:** `../../README.md` (event README — bounty/judging are a `TODO` stub),
   `../../../CONTRIBUTING.md` (PR-per-team submission process, "touch only your folder"),
   `../../../SECURITY.md` (never commit secrets/keys/seed phrases). *These define PROCESS, not the
   track requirements — those are in sources 1 & 2.*

### Spec requirements — VERBATIM quotes (source 1, the canonical doc)
Use these exact strings; do not re-summarise.
- *"Enforces access at the retrieval layer (not application layer), and without requiring an LLM call
  to make a permission decision."*
- *"Classification may use an LLM at write time, but the final enforcement path must be deterministic."*
- *"Maintain sub-200ms latency for permission checks (P99)."*
- *"Stay synchronized with source permissions under concurrent updates."*
- *"A summary, embedding, or note inherits the access constraints of its sources, and revoking a
  source propagates to the derivative."*
- *"Produce audit logs meeting regulatory requirements."*
- *"Your submission must run on open-weight models only" — no proprietary or closed models.*
- Bonus: *temporal access rules* (e.g. "leadership call notes unlock after 30 days"); *query-time
  inference prevention* (detect leaked information across permission boundaries).
- Deadline: *"Submissions close at Demo Day on 4 July — open your PR before judging begins."*

### What is OURS (design choices, NOT the spec — changeable, do not present as requirements)
- Modelling access as a per-item **category tag** matched against a per-role allowed-set
  (`check_item`). The spec says "deterministic / retrieval-layer / no-LLM-in-decision" — it does NOT
  mandate tags, exact-string matching, or categories. Other deterministic schemes (source-ACL mirror,
  attribute/policy rules) would also satisfy it. The access model is an OPEN design question.
- The tamper-evidence details we added beyond "regulatory audit logs": SHA-256 hash chain, sequence
  numbers, fsync durability, spreadsheet-formula defang, fail-closed `AuditError`. Sound, but ours.
- "Strict exact-match, case/whitespace-sensitive, reject non-set inputs" — our hardening, not the spec.

### Known unresolved
- The system is still a stub: memory items are hardcoded; no real store, agent, tagger, or model is
  wired yet. The "agent → tagger(LLM) → store → gated read" flow is designed but not built.
- "Inherits the access constraints of its sources" — we implemented revocation propagation only, NOT
  constraint inheritance. Gap vs the spec.
- "Stay synchronized with source permissions under concurrent updates" — not addressed.
- Latency: audit write currently reads the whole log per write (O(n)) — at-risk vs sub-200ms-at-scale.

### When the spec is unclear, conflicting, or silent — use judgment, don't stall
This applies to ANY gap: `TODO(maintainer)` stubs, two sources disagreeing, vague wording, or
something simply not covered. Be human about it — a good engineer doesn't freeze on ambiguity or go
robotic; they make the sensible call and keep moving. How:
- **Prefer the more specific, more authoritative source.** The filled-in Doc/event page (sources 1 & 2)
  beat the repo's `TODO` stub. A concrete number beats a vague phrase. The spec beats our SKILL gloss.
- **On a conflict, take the safer / stricter reading** when security or a deadline is at stake (e.g.
  two deadlines → aim for the earlier; ambiguous access rule → fail closed). Convenience never wins a
  tie over leakage.
- **Where the spec is genuinely silent, pick the most reasonable interpretation, state the assumption
  in one line, and proceed.** Don't demand certainty that doesn't exist; don't re-open it every turn.
- **Flag a blocker at most once.** If an ambiguity truly changes what to build, surface it briefly with
  a recommended default — then act on that default unless told otherwise. Don't litigate, don't loop.
- **Don't gold-plate the ambiguous bits.** Match effort to what's actually being judged; note the open
  question for the event mentors rather than over-engineering around a guess.
- Concrete example: deadline — repo says ~3 Jul EOD, source 1 says "PR before Demo Day, 4 July". Take
  the earlier (3 Jul), note it, move on; confirm with a mentor if it ever matters.

#### Real ambiguities that actually tripped up a past session (and the resolution)
Learn from these so you don't repeat them:
- **Repo brief is a stub.** `../../README.md` bounty + judging are `TODO` and the judging table is
  marked "TODO: finalize". → The real requirements are in sources 1 & 2, not the repo. Don't conclude
  "requirements undefined".
- **Two different judging rubrics.** Repo stub shows generic % weights (Autonomy 30 / Innovation 25 /
  …); sources 1 & 2 give MEASURABLE criteria (Security Correctness incl. *false-negative rate*,
  *sub-200ms P99 latency*, Auditability). → The measurable ones are authoritative; treat the % weights
  as a placeholder. Don't optimise to the placeholder.
- **"Inherits the access constraints of its sources" ≠ revocation.** Easy to read our `revoked_closure`
  as satisfying this. It does NOT — the spec wants a derivative to inherit its source's *permissions*,
  which is a superset of "revoke source → kill derivatives". Two distinct features; we only built one.
- **Quoting our own code as if it were the spec.** A past session asserted "per-item, exact-tag" as a
  requirement. It is NOT in any source — it's our design. → Only quote the three sources for
  requirements; mark our mechanisms as ours.
- **Cognee's write-time LLM is fine.** A past session wrongly implied Cognee was disqualified for using
  an LLM. The spec allows an LLM at WRITE time (classification); it's only banned from the permission
  DECISION. → The reason to be cautious with Cognee is scope/time and that its access control is
  dataset-level (not the deterministic per-decision gate the spec wants) — NOT its internal LLM.
- **The Google Doc won't render from the editor URL.** Fetch `…/export?format=txt` and follow the
  307 redirect to the `googleusercontent.com` export host to get the body.
- **The whole thing is still a stub.** Items are hardcoded; there is no live store/agent/tagger/model.
  Don't describe built features as if the end-to-end product exists — be honest about what's real.

## Architecture & current state

> This describes what we BUILT so far — it is our current design, not a spec requirement. The access
> model (per-item category tags) is an OPEN choice (see "What is OURS" above); it could change to a
> source-ACL mirror or attribute/policy scheme and still satisfy the spec.

- `bouncer.py` — the deterministic "bouncer":
  - `MemoryItem(id, category, text)`, `Decision(item, allowed, reason)`
  - `check_item(allowed_categories, item)` — the single security chokepoint; defensive/total/fail-closed.
  - `filter_allowed(allowed, items)` — pure, no side effects (easy to unit-test).
  - `retrieve(user, allowed, items, log_path=...)` — the AUDITED access path; logs every decision,
    fails closed on audit failure. Real callers use this.
- `audit.py` — tamper-evident audit log:
  - `log_decision(...)` appends one row (`seq, timestamp, user, item_id, category, decision, reason,
    row_hash`), flushes + fsyncs for durability.
  - `verify(path)` recomputes the hash chain AND cross-checks the checkpoint/anchor; returns
    `(ok, message)` naming the first broken row.
  - A **checkpoint / running-tally** side file (`audit_log.csv.checkpoint`) records `(count, head-hash)`
    after every write → O(1) appends + end-truncation detection; it is itself an append-only hash chain
    and is mirrored to an off-host `.anchor`. `read_log`, `AuditError`, `_defang`, `_compute_row_hash`.
- `memory.py` — load-time resolvers: `load_config`/`allowed_categories_for_user` (roles→set,
  deny beats allow, `*` wildcard) + `load_lineage`/`revoked_closure`/`revoked_ids` (lineage graph →
  full transitive revoked set). All fail-closed via `ConfigError`.
- `cli.py` — the single entrypoint: `python cli.py <user>` wires the loaders + bouncer + audit;
  `load_items()` reads the memory store. It invents no policy/tag/revocation — only wires real loaders
  to the real gate, exactly as a production caller would.
- `users.json` (roles→allow/deny categories, users→roles), `lineage.json` (`derived_from` + `revoked`),
  and `memory_store.json` (the memory items as DATA, not hardcoded). NOTE: built as JSON, not the
  `users.yaml` originally sketched (stdlib, no dep).
- `test_bouncer.py` — the test suite. Every fix gets a regression test here.
- `ToDo_audit-log.md` — audit roadmap. Deferred upside: blockchain anchoring (Kaspa — anchor only
  the chain hash, never raw records), retention segmentation, extra fields (`event_type`,
  `user_location`/`item_jurisdiction` for the cross-border bonus).
- In-repo docs: `HANDOFF.md` (start-here orientation + OS-agnostic run steps), `TODO.md` (master
  backlog), `FEATURES.md`, `NAMING_AND_TRADEMARK_NOTES.md`, `ToDo_audit-log.md`.
  Project display name: **GOVhence MEM-Ø** (`MEM-0` when typed). NOTE: this `SKILL.md` is itself
  committed to the repo — to hand off, copy it verbatim into the new machine's skills folder. No
  re-interpretation needed; the file IS the handover.

### Intended build order (each milestone verified before the next)
> The PLAN, not the status. **Current milestone progress and test count live in `HANDOFF.md`.**
M1 bouncer → M2 tests → audit log + tamper-evidence → M3 `users.json` + `memory.py` loaders
(roles→allowed; `exec` = allow `*` deny `legal`) → M5 lineage revocation (revoke a source → propagates
to all derivatives; revoked beats allowed) → M6 one `cli.py` entrypoint (wire loader+bouncer+audit; no
hardcoded values) → M7 real semantic store + open-weight embeddings via **BasedAPIs** (bouncer still
filters results) → M8 write-time LLM classification via BasedAPIs (label only, never decide).

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
- **Ponytail principle — follow the SOURCE, don't guess it.** The authority is the repo, not this
  gloss: read and apply <https://github.com/DietrichGebert/ponytail>. Faithful hook (not a substitute
  for reading it): *"the best code is the code you never wrote"* — walk the decision ladder (does it
  need to exist at all? → reuse what's already here → stdlib → native platform → installed dep → one
  line → only then write the minimum) and **stop at the first rung that holds**. **Lazy about the
  solution, never about reading; lazy, NOT negligent** — trust-boundary validation, data-loss handling,
  and security are NEVER on the chopping block (decisive for a security project like this one).
- **A fix without a test rots.** Every defect fix gets a regression test in `test_bouncer.py`, and
  you run the full suite (confirm nothing old broke) before declaring done.
- **Verify with evidence, not claims.** Run the code, show real output / exit codes / the actual
  audit log; prove behaviour rather than asserting it.
- **Don't guess external interfaces — read the real thing.** For any library, API, CLI flag, standard,
  or version, fetch the actual docs/source before using it; never code from memory (the spec/Ponytail
  "source is the authority" rule, generalised).
- **Know the blast radius before touching shared code.** Before changing a shared function/signature,
  find its call sites + tests; a local fix that breaks a caller isn't done.
- **One logical change per commit; never leave the suite red.** Small, reviewable, revertable steps;
  the working tree always passes.
- **Match the surrounding code.** New code reads like its neighbours — their conventions, naming,
  idioms, error handling. Consistency over preference.

## Lessons learned (gotchas that already bit us — don't repeat them)

- **No demo or runtime artifacts in committed code.** The audit log is GENERATED, not source:
  `audit_log.csv` and its `.checkpoint`/`.anchor` side files are git-ignored (`audit_log.csv*`) and
  must never be committed. Tests and probes write to a TEMP path, never the real log.
- **Totality means validating element TYPES, not just the container.** A JSON value can pass an
  `isinstance(x, list)` check yet contain a non-string / unhashable element that raises a raw
  `TypeError` inside `set()` — escaping the fail-closed `ConfigError` contract and crashing the caller.
  Validate every element; any malformed shape must raise `ConfigError`, never a bare exception.
- **An item's `id` is the audit key AND the revocation key.** The store loader must require it to be a
  NON-EMPTY STRING. A non-string id is a fail-OPEN: it can never match the revocation set and it
  corrupts the audit trail. (`category`, by contrast, is passed through and denied by the gate.)
- **Windows line-endings silently break a hash chain.** Open any hash-chained side file with
  `newline=""` (or write `\n` explicitly). Text mode on Windows turns `\n` into `\r\n`, so a binary
  tail-read sees `hash\r` while `splitlines()` sees `hash`, and the chain fails to verify on the
  system's own untampered log.
- **Verify by trying, not by trusting.** The line-ending bug and a fail-open id leak both slipped past
  code review and were caught only by RUNNING the tests + the adversarial stress harness. A green
  board that hides a real hole is a failure; prove behaviour with real output before declaring done.

## Keep the trackers current (no stale files)

A doc that lags the code is a bug. Any change that affects behaviour, status, or features updates the
relevant tracker IN THE SAME change. Who owns what:

| File | Holds | Update when |
|------|-------|-------------|
| `README.md` | the public pitch / "what it does" | a headline feature or the story changes |
| `FEATURES.md` | one-line feature datasheet (+ test count) | a feature ships |
| `HANDOFF.md` | START-HERE orientation + **all current status** (milestones done/next, test count, new files) | progress changes |
| `TODO.md` | master backlog + **open bugs** | an item is added / done, or a bug is found |
| `SKILL.md` | timeless how-to, rules, conventions, lessons (this file) | the WAY we work changes |
| `ToDo_audit-log.md` · `NAMING_AND_TRADEMARK_NOTES.md` | their own topic | that topic changes |

Rule of thumb: **status → HANDOFF · backlog/bugs → TODO · features → FEATURES + README ·
how-to/rules/lessons → SKILL.** Never put status or open bugs in this SKILL.

**SKILL is committed TWICE.** This project-folder `SKILL.md` is canonical (it ships with the project, so
it stays portable). The copy that actually LOADS is `.claude/skills/develop-memory-governance/SKILL.md`
— after editing this file, copy it across so the two stay byte-identical:
`cp SKILL.md .claude/skills/develop-memory-governance/SKILL.md`. A drifted copy = a stale skill.

**Independent adversarial review** (no dedicated file needed): spin a reviewer agent that reads the diff,
writes findings to a SCRATCH file, and NEVER edits code — and/or run an adversarial stress harness.
Verify by trying, not by trusting.

## Hard constraints (hackathon)

- **Open-weight models only** in the product (Llama/Qwen/Mistral/etc., served via BasedAPIs). No
  closed models in the loop.
- **Never commit secrets.** Use `.env.example` with placeholders; keep real values local. Throwaway
  wallet only if doing the blockchain-anchoring upside.
- The PR (at submission time) must touch ONLY the team folder. Folder names are lowercase-hyphenated.
- Judging: see the spec sources above — the MEASURABLE criteria (security correctness incl.
  false-negative rate, sub-200ms P99 latency, auditability) are authoritative. The generic % weights
  (autonomy 30 / innovation 25 / sponsor-tech 20 / usefulness 15 / demo 10) are the repo stub's
  placeholder — don't optimise to them over the measurable ones.
- Deadline: repo says ~3 Jul EOD; spec says "PR before Demo Day, 4 July". Aim for the earlier (3 Jul);
  confirm with a mentor.

## Definition of done for any change

1. Code is simple, readable, and explained in plain terms to the user.
2. It honours the verbatim spec requirements above (deterministic enforcement at the retrieval layer,
   no LLM in the permission decision, regulatory audit logs, open-weight only). Where our current
   design adds more (fail-closed, hash-chained audit), keep that — but don't confuse it with the spec.
3. New behaviour has a regression test; the FULL suite passes (exit code 0).
4. You showed the user real evidence it works, and (when asked) committed/pushed to the PRIVATE repo
   after confirming no secrets and that it stayed private.
5. The relevant trackers are updated in the SAME change (status → HANDOFF, features → FEATURES/README,
   backlog/bugs → TODO) and the two SKILL copies are byte-identical — no stale file.

## Milestone gate — heavier QA at each major milestone (not every change)

The "Definition of done" above is the LIGHT gate. At each MAJOR milestone (a shipped feature or
checkpoint), run the HEAVY gate too — without being asked:

1. **Reality check** — every claim in the docs is TRUE and re-verified: the full suite passes at the
   real count; the stated invariants (e.g. fail-closed, no-LLM-in-the-decision) still hold; what the
   docs say is built actually is. Run it, don't assert it.
2. **Adversarial stress + robustness** — hammer hostile/malformed inputs (the stress harness): wrong
   types, unicode/homoglyphs, injection, bad config → invariant: ZERO leaks, ZERO crashes, fail-closed.
3. **Scale (proportionate)** — spot-check the hot paths stay cheap at size (e.g. O(1) audit append; a
   large log/retrieval stays within the latency budget). Right-size the effort; not a load test.
4. **Security review** — an independent adversarial pass over the diff (writes findings to a scratch
   file, never edits code): the absolute rules hold, no fail-OPEN, audit complete + tamper-evident.

Findings → fix critical/cheap now, log the rest in `TODO.md`, then update the trackers.
