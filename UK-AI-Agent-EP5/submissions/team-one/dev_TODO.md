# dev_TODO — GOVhence live pipeline (WIP handover)

> Developer working notes for branch **`feat/govhence-pipeline`**. This is NOT the curated backlog
> (that's `TODO.md`). `main` is clean at `7f5493a`. Working-first build of `PRD.md`, reusing
> bouncer/memory/audit + stdlib (Ponytail). Keep the name **`bouncer`** (= the PRD's DeterminExtractor).
> LLM roles are rule-based **stubs** behind a clean seam (no open-weight model wired here yet); **none
> makes the access decision** (absolute rule 2).

## Status — ✅ GREEN: **106 pass** · `python pipeline.py --demo` runs the full story · **5 increments + R2 done**
> (1) working scaffold · (2) relevance ranking + top-k cap · (3) salient content-word tags + proven
> memory loop · (4) security pass (injection blocked · total on adversarial input · write-time RBAC
> scoping) · (5) scripted `--demo` · **R2 audit-write totality (commit `3144c4f`)**. Run one turn:
> `python pipeline.py bob "<msg>"`.
- [x] `bouncer.MemoryItem` += `tags` (relevance only, never access)   *(committed ae9e857)*
- [x] `users.json` += `shared` category (driver; exec via `*`)         *(committed ae9e857)*
- [x] `cli.load_items` reads `tags`
- [x] `cocoshamem.seed.json` — 7 seed memories (incl. `shared` / `financials` / `legal`)
- [x] `agents.py` — Classifier / Judge / Memoriser / Responder stubs + tag hygiene
- [x] `pipeline.py` — verify → classify → relevance pre-filter → **bouncer access filter (audited)** → MemoryLane → Responder; write-path Judge → Memoriser → append runtime store; + CLI
- [x] `.gitignore` += `cocoshamem.json` (runtime store; seed committed)
- [x] `test_pipeline.py`

## ✅ Fixed — the 1 red test
`agents.memorise()` now returns `None` for a query (`cls.kind == "query"`) — defensive; the Judge
gates it upstream too. Suite green (94).

## Remaining (next increments)
**Blocking security hardening (do before ship — see `TODO.md`):**
- ✅ **R2 done** — audit write is now TOTAL (fail-closed on oversized field / unpaired surrogate).
  Fixed at `audit._defang` (encode-safe + length-capped) + widened `log_decision` except. Commit `3144c4f`.
- ⬜ **R1 — serialize concurrent audit writes.** Two writers read the same last seq+hash (no lock) →
  duplicate seq, forked hash chain, `verify()` breaks. Fix: one critical section around
  `_last_link` → append → `_append_checkpoint` in `audit.log_decision`, using a **cross-platform** lock
  (lockfile via `os.open(..., O_CREAT|O_EXCL)` + bounded retry, reusing the atomic-replace pattern in
  `audit._replace_with_retry`; add a `threading.Lock` for in-process threads). **SKILL forbids raw
  `fcntl`/`msvcrt`.** Fail closed if the lock can't be taken. New concurrency test (spawn N threads →
  seqs 0..N-1 unique, `verify()` ok).
- ⬜ **R3 — derived memory inherits its source's access constraints.** Today the Memoriser sets category
  only from the current message; the write path records no `derived_from` → a summary of a `financials`
  item can be stored `shared` (leak). Fix at WRITE time: (1) define restrictiveness as an **explicit
  rank map in config** *(user's chosen approach)* loaded fail-closed; (2) add `derived_from` to
  `MemoryDraft` + write it in `pipeline._append_memory` (and `lineage.json`); (3) computed category =
  MOST-RESTRICTIVE of {own} ∪ {each source's}, reusing the `memory.revoked_closure` graph-walk shape.
  Bouncer stays a flat set gate.

**Feature work (after hardening):**
- **Wire a real open-weight model** behind the `agents.*` seam (BasedAPIs) — stubs stay as the offline fallback (M8).
- **Real semantic store** + embeddings for CocoShaMem (M7); the bouncer still filters results.
- **True async** write path (thread the write side; today the read path already completes before the write).
- Pipeline revocation demo (reuse `memory.revoked_ids`); richer tag-synonym reuse.
- Fold the pipeline into the docs (README / PRD status) before merging to `main`.

## Key design decisions (autonomous best-guesses — revisit if wrong)
- relevance = message-tags ∩ item.tags; **ACCESS is unchanged** (`bouncer.check_item`), audited.
- Memoriser assigns the access category at WRITE time: `shared` default; `financials` / `legal` if sensitive.
- runtime memory-writes → git-ignored `cocoshamem.json`, seeded from committed `cocoshamem.seed.json`.
- role→department map in `agents.ROLE_DEPARTMENT` for user tags.
- **Security property that holds:** `mem-financials` is tagged `london`, so a "london" query makes it
  *relevant* to bob (a driver) yet the bouncer still **DENIES** it (financials ∉ bob) and logs the DENY.
