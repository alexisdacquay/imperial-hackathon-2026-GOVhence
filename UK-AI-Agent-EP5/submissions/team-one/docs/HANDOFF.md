# HANDOFF — start here (for a new developer or AI agent)

> **Purpose:** everything a fresh collaborator needs to continue **GOVhence MEM-Ø** without any
> outside context. Self-contained and OS-agnostic. Pairs with `SKILL.md` (the formal operating
> manual): read this for orientation and run steps; load `SKILL.md` to adopt the full rules and
> working style.

---

## 1. What this project is

A hackathon submission for the **BasedAI track — "Enterprise Memory Governance at Scale."**
It is a **permission-aware layer over ONE shared memory** used by many AI agents: each user
retrieves only the memory items their role is allowed to see, every access is decided by
**deterministic code (never an LLM)**, and every decision is written to a **tamper-evident audit
log**. Deny-by-default, fail-closed — *zero-trust memory*.

- Lives in: `UK-AI-Agent-EP5/submissions/team-one/` (a copy of the `BasedAICo/hackathons` repo).
- Display name **GOVhence MEM-Ø**; typed as `MEM-0` in code/CLI/filenames. Folder stays `team-one`
  (hackathon rule: lowercase-hyphenated). Branding/trademark rationale: `NAMING_AND_TRADEMARK_NOTES.md`.
- Deadline: submit before **Demo Day, 4 Jul 2026**. The PR at submission must touch ONLY this folder.

---

## 2. THE 4 ABSOLUTE RULES — never violate these

These are the spine of the project. Any change must honour all four.

1. **Strict exact-match enforcement, FAIL-CLOSED.** The read-time access decision requires the
   user's **clearances** to cover **ALL** the memory's **labels** (`labels ⊆ clearances`), compared
   EXACTLY (case- and whitespace-sensitive strings). Whitelist-only: NO deny list, NO wildcard.
   A memory with NO labels is visible to NOBODY (an empty set passes every subset check — fail-open
   otherwise). NEVER normalize, interpret, fuzzy-match, or LLM-guess at read time. Any mismatch /
   unknown user / wrong type / internal error ⇒ **DENY**; malformed config/store data ⇒ loud
   `ConfigError` (never a bare `TypeError` escaping from set operations).
2. **No LLM in the access decision.** A model may classify/label content at **WRITE time only**
   (reusing a canonical tag vocabulary). The read path is pure deterministic code. The track
   requires: *"enforcement must be deterministic."*
3. **The audit log is a legal record, not a demo artifact.** COMPLETE (every ALLOW and DENY, 100%
   coverage — there is NO "sample"), append-only, UTC-timestamped, tamper-evident (sequence number +
   SHA-256 hash chain), retained. A logging failure must FAIL CLOSED (raise `AuditError`, refuse
   access). Never silently trim/delete records — if retention ever becomes a concern, PROPOSE the
   trade-off, don't decide it. Defang spreadsheet-formula injection (values starting with `= + - @`).
4. **Enforcement and its logging live at the RETRIEVAL layer** — inside the access decision point
   (`bouncer.check_item` / `retrieve`), not in an app/API layer above it.

---

## 3. Architecture & current state (what's built)

**Status (branch `feat/govhence-pipeline`): M1–M6 done + tamper-evident audit checkpoint/anchor,
PLUS the live GOVhence pipeline scaffold (Classifier/Judge/Memoriser/Responder as deterministic
stubs behind a clean seam + end-to-end read/write flow) AND security fix R2 (audit write is now
TOTAL — fail-closed on adversarial values). NEW (2 Jul): the access model is now **whitelist-only
labels/clearances** (government-classification style, ALL-match; deny/`*` removed) with the
DEFINITIVE vocabulary `topics` (content, ANY-match, from the LLM — never grants access) /
`labels` (on memories) / `clearances` (held via roles in `users.json`); `src/bouncer.py` is a
REAL gate (loads `cocoshamem.seed.json` + `users.json` itself, validates types, `ConfigError`
fail-closed) with 19 unit tests. ALSO NEW (2 Jul): the **Memoriser is a real LLM role** (V2 done) —
write-time security labelling from the known vocabulary (`bouncer.all_labels`), guarded by
deterministic code: **fail-closed writes** (offline/junk → candidate refused, store untouched) and
the **writer cap** (labels ⊆ the writer's own clearances; cap on labels only, topic words free).
The automated suite passes (exit 0).**
> `main` is the stable baseline (M1–M6, no pipeline). The pipeline + R2 live on
> `feat/govhence-pipeline` — work here. Next: R1 (serialize concurrent audit writes) and R3
> (derived-memory inherits its source's access constraints), then wire a real open-weight model
> (M7/M8) behind the `agents.*` seam. See `dev_TODO.md` (this branch) and `TODO.md`.

| File | What it is |
|------|------------|
| `bouncer.py` | The deterministic gate. `MemoryItem(id, category, text)`, `Decision(item, allowed, reason)`, `check_item(allowed_categories, item, revoked_ids=frozenset())` — the single chokepoint; `filter_allowed(...)` — pure; `retrieve(user, allowed, items, log_path=..., revoked_ids=...)` — the AUDITED path real callers use. |
| `memory.py` | Load-time resolvers. `load_config`/`allowed_categories_for_user` (roles→allowed set, deny beats allow, `*` wildcard) and `load_lineage`/`revoked_closure`/`revoked_ids` (lineage graph → full transitive revoked set). All fail-closed via `ConfigError`. |
| `audit.py` | Tamper-evident log. `log_decision(...)` appends one row (`seq…row_hash`), flush+fsync. `verify()` recomputes the hash chain AND cross-checks the checkpoint/anchor. A **checkpoint/running-tally** side file records `(count, head-hash)` per write → O(1) appends + end-truncation detection; mirrored to an off-host `.anchor`. `read_log`, `AuditError`, `_defang` — **`_defang` now also makes every field encode-safe + length-capped so no adversarial value can crash the write (R2, fail-closed).** |
| `cli.py` | The single entrypoint — `python cli.py <user>` wires loaders + bouncer + audit; `load_items()` reads the store. Invents no policy. |
| `agents.py` *(branch)* | The PRD's LLM roles — Classifier / Judge / Memoriser / Responder — as DETERMINISTIC rule-based stubs behind a stable seam. **NONE makes the access decision** (rule 2); the Memoriser assigns an access category at WRITE time. Swap a stub for a real open-weight model (BasedAPIs) by re-implementing the same signature. |
| `pipeline.py` *(branch)* | End-to-end orchestration: verify → classify → tag-relevance pre-filter → **`bouncer.retrieve` (the audited access gate)** → top-k MemoryLane → Responder; write path Judge → Memoriser → append runtime store. Relevance NEVER bypasses access. `python pipeline.py <user> "<msg>"`, `--demo`. |
| `cocoshamem.seed.json` *(branch)* | Seed for CocoShaMem (the corporate shared memory). Runtime store `cocoshamem.json` is regenerated from it and git-ignored. |
| `users.json` | Roles → allow/deny categories; users → roles. (`exec` = allow `*`, deny `legal`; `driver` also allows `shared`.) |
| `lineage.json` | Item provenance: `derived_from` (child→parents) + `revoked` sources. |
| `memory_store.json` | The memory items as DATA (no longer hardcoded). |
| `test_bouncer.py` / `test_pipeline.py` | The test suite: adversarial / fail-closed / tamper-evidence / lineage / cli / checkpoint / R2-totality / pipeline (classify, judge, memorise, relevance-never-bypasses-access, memory-loop). Every fix gets a regression test here. |
| `audit_log.csv` (+ `.checkpoint`/`.anchor`) | The runtime audit log + its tally side files — GENERATED at run time, git-ignored (`audit_log.csv*`), never committed. |
| `SKILL.md` | The formal operating manual (rules, conventions, working style, definition of done). Load this to work on the project as an agent. |

**Key design idea:** all policy work (role expansion, deny subtraction, lineage graph traversal)
happens **once at load time in `memory.py`**, producing two plain `set`s. The gate then does nothing
but exact set membership — which is why it stays deterministic and can't be tricked into fuzzy
matching. "Revoked beats allowed": a revoked item is denied even if its category is allowed.

---

## 4. How to run it (any OS)

The core is **pure Python standard library** (built/tested on **Python 3.13**, works on 3.11+).
The ONLY third-party dependency is `pytest`, and only for tests.

```bash
# from the team-one folder. Use whatever Python launches on your machine:
#   macOS/Linux: python3      Windows: python      (or a full path if PATH lacks one)

# (optional) create an isolated environment + install the test runner
python3 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt # installs pytest

# 1. See access + lineage revocation enforced, and the audit log get written
python3 bouncer.py

# 2. See roles resolve to allowed sets, and the lineage graph resolve to the revoked closure
python3 memory.py

# 3. Run the full suite — exit code 0 means all pass
python3 -m pytest -v

# 4. Prove the audit log was not tampered with
python3 -c "import audit; print(audit.verify())"
```

> **Probes/throwaway scripts:** put them in a temp/scratch dir, NOT the project folder. In any
> probe or test, use a TEMPORARY log file — NEVER write to the real `audit_log.csv`.

---

## 5. Working style (how this team wants you to work)

- **The user is new to coding.** Explain every technical term plainly (what `venv`/`commit`/`suite`
  mean), inside command descriptions too. Favour longer, clearer summaries. Never approve-gate them
  on a command full of unexplained jargon.
- **One small step at a time.** Build the smallest testable unit, RUN it, SHOW it working, explain
  it, let them verify, then check before the next. Don't scaffold the whole stack at once.
- **Don't batch decision questions.** Answer the question first, in prose. Ask design/tooling
  questions one at a time, only when that decision is actually next — not as a wall of multiple-choice.
- **Security-first; propose, don't assume.** On any trade-off, lead with the safe option and a clear
  proposal for the user to choose. Never quietly pick convenience over completeness/safety.
- **Ponytail principle — follow the SOURCE, don't guess it.** Read and apply
  <https://github.com/DietrichGebert/ponytail> (the authority, not a paraphrase). Faithful hook:
  *"the best code is the code you never wrote"* — walk the decision ladder (need it at all? → reuse →
  stdlib → platform → dep → one line → only then write the minimum), **stop at the first rung that
  holds**. **Lazy, NOT negligent** — trust-boundary validation, data-loss handling, and security are
  NEVER on the chopping block.
- **A fix without a test rots.** Every defect fix gets a regression test in `test_bouncer.py`; run
  the FULL suite (confirm nothing old broke) before declaring done.
- **Verify with evidence, not claims.** Run the code; show real output / exit codes / the actual
  audit log. Prove behaviour, don't assert it.

## Definition of done (every change)
1. Simple, readable, explained in plain terms. 2. Honours all 4 absolute rules. 3. New behaviour has
a regression test and the FULL suite passes (exit 0). 4. You showed real evidence it works.

---

## 6. Hard constraints (hackathon)

- **Open-weight models only** in the product (Llama/Qwen/Mistral via **BasedAPIs**). No closed models
  (no GPT/Claude/Gemini) in the loop. LLMs may LABEL at write time, never DECIDE access.
- **Never commit secrets.** Use `.env.example` with placeholders; keep real `.env` local. Throwaway
  wallet only if doing the optional blockchain-anchoring upside.
- Judging weights: autonomy/tech 30% · innovation 25% · use of BasedAI/sponsor tech 20% ·
  real-world usefulness 15% · demo 10%.

---

## 7. What to read next (all in this folder)

- **`SKILL.md`** — the formal operating manual: the same rules above plus full conventions, working
  style, and definition of done. Copy this verbatim into a new machine's skills folder to hand off.
- **`TODO.md`** — the master backlog (numbered, self-contained). What's done + the new feature ideas
  (crypto-chain signing, police/whistle-blower agents, robustness+demo generator, GUI, tag-scoping).
- **`FEATURES.md`** — one-line datasheet of implemented features + roadmap.
- **`PRD.md`** — next-phase requirements: the live memory-governance pipeline (intake → analysis →
  deterministic retrieval → response → async memory-write) on top of the current core.
- **`ToDo_audit-log.md`** — deep audit-log roadmap + the standards/citations behind the design.
- *Independent adversarial review:* see `SKILL.md` → "Keep the trackers current" (spin a reviewer that
  writes to a scratch file and never edits code, and/or run the stress harness) — no dedicated file.
- **`README.md`** — the public/blog-style pitch (and the ASCII banner).
- **`NAMING_AND_TRADEMARK_NOTES.md`** — brand decision (GOVhence = the brand; MEM-Ø = edition tag,
  not trademarked) and the trademark research.

### Milestone roadmap
M1 bouncer ✅ · M2 tests ✅ · audit log + tamper-evidence ✅ · M3 users.json + loaders ✅ ·
M5 lineage revocation ✅ · M6 one `cli.py` entrypoint ✅ (wires loader+bouncer+audit; items as data,
no hardcoded values) · audit checkpoint/anchor ✅ (O(1) appends + end-truncation alarm) ·
live pipeline scaffold ✅ *(branch: agents/pipeline stubs, end-to-end)* · R2 audit-write totality ✅
*(branch: fail-closed on adversarial values)* · **R1 (next) serialize concurrent audit writes**
(cross-platform lock — NOT raw fcntl/msvcrt) · **R3 derived-memory inherits source constraints**
(most-restrictive category at write time; ordering via an explicit rank map in config) ·
**M7 real semantic store + open-weight embeddings via BasedAPIs** (bouncer still filters results) ·
M8 write-time LLM classification via BasedAPIs (label only).

---

> **First thing to do on pickup:** confirm you're on the right branch (`git branch --show-current`
> → `feat/govhence-pipeline` for pipeline/R-series work; `main` for the stable baseline), then run
> `python3 -m pytest -v` and confirm **exit code 0 (all pass)**.
> That proves the environment works and nothing is broken before you change anything.
