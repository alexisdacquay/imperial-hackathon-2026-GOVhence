```
    ██████╗  ██████╗ ██╗   ██╗██╗  ██╗███████╗███╗   ██╗ ██████╗███████╗
   ██╔════╝ ██╔═══██╗██║   ██║██║  ██║██╔════╝████╗  ██║██╔════╝██╔════╝
   ██║  ███╗██║   ██║██║   ██║███████║█████╗  ██╔██╗ ██║██║     █████╗
   ██║   ██║██║   ██║╚██╗ ██╔╝██╔══██║██╔══╝  ██║╚██╗██║██║     ██╔══╝
   ╚██████╔╝╚██████╔╝ ╚████╔╝ ██║  ██║███████╗██║ ╚████║╚██████╗███████╗
    ╚═════╝  ╚═════╝   ╚═══╝  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝ ╚═════╝╚══════╝
                ┌─────────────────────────────────────┐
                │   M E M - Ø   ·   zero-trust memory  │
                └─────────────────────────────────────┘
        one shared memory · zero leaks · provable to auditors
```

> **Give a whole company of AI agents one shared brain — without any of them seeing what they
> shouldn't.** Deterministic access control, tamper-evident audit trail, and revocation that
> chases information through everything it touched. No AI in the security decision. Ever.

**Team:** team-one  ·  **Members:** `@your-handle (Name)`, …  ·  **Track:** UK-AI-Agent-EP5 — BasedAI

`tests passing` · `Python stdlib only` · `open-weight models only` · `fail-closed by design`

---

## The problem, in one breath

```
   Many AI agents.            One shared memory.          A leak waiting to happen.
         o  o  o        ───►        (everything)     ───►       driver reads the
         o  o  o                                                 CEO's financials
```

Shared memory makes agents smarter — they stop repeating work and share context. But put
**everything in one place** and suddenly the logistics driver's bot can read the CEO's financials,
and a contractor's agent can open confidential legal files.

**The mission:** keep the memory **shared but fenced** — everyone reads the same brain, but each
person only ever sees the pages their role unlocks. And you must be able to **prove it** to a
regulator.

---

## The big idea

```
   ┌──────────────────────────────────────────────────────────────┐
   │   The AI NEVER decides who gets access.   Plain code does.    │
   └──────────────────────────────────────────────────────────────┘
```

- An AI can be **tricked, jailbroken, or hallucinate** → never trust it with the keys.
- A **deterministic code check** can't be talked out of a "no." Same input, same answer, every time.
- Every memory item wears a **category tag** (`schedules`, `financials`, `legal`…). Your role
  unlocks a set of tags. Access = *is this tag in your set?* — an **exact, strict** match.
- Every decision is **logged immutably**. Revoke a source and the block **chases it everywhere**.
- **We verify by trying, not by trusting.** A real guard doesn't glance at the chained gate and
  assume it's locked — they *rattle it*. Our security actively attacks itself: it probes its own
  defences for ways in, rather than asserting they hold. Active verification over passive trust.

> This is exactly what the track demands: *"enforcement must be deterministic."* We took it literally.

---

## How a request flows

```
         user (has a ROLE)
         │
         ▼
   ╔═══════════════════════════════════════════════════════════╗
   ║   PERMISSION LAYER   —   pure code, zero AI in the loop    ║
   ║                                                           ║
   ║   1.  role  ─────────────►  set of allowed tags    users.json
   ║   2.  apply revocations (+ everything derived)     lineage.json
   ║   3.  each item:   tag in set?    ALLOW / DENY      ◄ the gate
   ║   4.  write the decision to the audit trail  ────► audit_log.csv
   ║                                                      (tamper-evident)
   ╚═══════════════════════════════════════════════════════════╝
         │
         ▼
         only the permitted items come back
```

---

## See it in 10 seconds

```
$ python bouncer.py
────────────────────────────────────────────────────────────────────────
User: bob (driver, logistics)   allowed: schedules, opening-hours, goods-weights-volumes
Revoked items: item1                                       (a leaked source)
────────────────────────────────────────────────────────────────────────
  DENY   item1   schedules              item is REVOKED  ← revoked beats allowed
  ALLOW  item2   opening-hours          in bob's allowed set
  ALLOW  item3   goods-weights-volumes  in bob's allowed set
  DENY   item4   financials             not in bob's allowed set
  DENY   item5   legal                  not in bob's allowed set
────────────────────────────────────────────────────────────────────────
  Returned 2 of 5 — every decision written to the audit trail
```

`item1`'s category (`schedules`) is one bob is *allowed* to see — but it was **revoked**, so it is
denied anyway. The financials and legal files? **Never even leave the store.**

---

## What it does — the feature lineup

> Every feature below is **live and covered by automated tests** (the suite passes, exit 0). ✅

### 1 · Deterministic access control — *the bouncer*
One strict, exact comparison decides every item. **No AI in the decision.** Identical every time,
fully auditable.

### 2 · Fail-closed by *default*
Unknown tag? Malformed input? Bad config? Look-alike Unicode trickery? **→ DENY.**
- Never "fails open" (never accidentally grants)
- Battle-tested against adversarial inputs — wrong data types, homoglyphs, empty profiles
- When in doubt, **withhold** — leaking is never an option

### 3 · Role-based permissions, *outside the code*
Who-sees-what lives in a plain editable file ([users.json](users.json)).
- Roles → allowed categories
- "Allow everything **except** X" (e.g. an exec who sees all *but* legal)
- Admins change access by editing one file — **zero code changes**

### 4 · Config that *catches its own mistakes*
- Unknown user / unknown role / typo'd category / corrupt file → **stops with a clear error**
- A misconfig in a governance tool gets **flagged**, never silently waved through

### 5 · Lineage revocation — *the showstopper*
```
   revoke  source                                    the block PROPAGATES
            │  └─derived─► summary                    to every derivative,
            │              └─derived─► embedding       however many hops deep
            ▼
        all of them denied — even if their tag was "allowed"
```
- Revoke a **source** → every item **derived from it** is revoked too, transitively
- **"Revoked beats allowed"** — a revoked item is denied even if its category is permitted
- This is the requirement **most systems get wrong**. We don't.

### 6 · Regulator-grade audit log
- **Every** decision logged — grants **and** refusals
- Captures **who · what · when (UTC) · outcome · why**
- Append-only · **no sampling, ever** — the *complete* record is retained
- Reconstruct *"who saw what, when"* for any item — including blocked attempts

### 7 · Tamper-evident — *the log can't be faked*
```
   row 0 ──hash──► row 1 ──hash──► row 2 ──hash──► row 3
                         ▲
            edit / delete / reorder ANY row  ──►  chain breaks  ──►  detected
```
- Sequence numbers → a deleted record leaves a **visible gap**
- SHA-256 **hash chain** → any edit/insert/reorder is **caught**, pointing to the exact row
- Built-in `verify()` integrity check — **court-credible** evidence
- Standards-aligned (NIST integrity / WORM-alternative) — **no database, no blockchain needed**
- **Checkpoint / running-tally** → catches **end-truncation** (rows shaved off the tail) a bare chain can't, keeps appends **O(1)** at any size, and mirrors the latest tally to an off-host **anchor** (the Certificate-Transparency / CloudTrail / QLDB pattern)

### 8 · No log → no access
- If a decision can't be recorded, the access is **refused**
- On a 100%-coverage system, an *unlogged* access is a breach — so we forbid it

### 9 · Injection-safe audit trail
- Malicious values (e.g. starting with `=`) can't run as spreadsheet formulas
- Can't forge or corrupt records — **reviewing the log is safe**

---

## Run it yourself

```bash
# Python 3.11+ (built on 3.13). Core needs NO external services.

python -m venv .venv && .venv/Scripts/activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python bouncer.py    # watch access decisions, live
python memory.py     # see each role resolve to its allowed tags
python -c "import audit; print(audit.verify())"    # prove the log is untampered
python -m pytest -v  # the whole suite — the proof every feature works (exit 0 = all pass)
```

---

## Under the hood

| | |
|---|---|
| **AI in the access decision** | **None.** Deterministic by design. (Open-weight models help only at *write* time later.) |
| **Stack** | Python 3.13 · **standard library only** for the core — least code that works |
| **Models** | open-weight only (BasedAPIs planned for write-time tagging + semantic retrieval) |
| **Tests** | `pytest` — covering access, fail-closed, config, lineage, audit + tamper-evidence + checkpoint/truncation + audit-write totality (R2) + the live pipeline |

---

## What's next

- **Semantic retrieval** over a real store (open-weight embeddings) — the AI only ever sees
  *already-permitted* content
- **Write-time classification** by an open-weight model — it *labels*, it never *decides*
- **External anchoring** of the audit fingerprint (e.g. Kaspa) — beat even an insider who
  rewrites the whole local log ([design notes](ToDo_audit-log.md))
- **Sub-200ms at scale** + live sync with external source ACLs

---

```
   ┌────────────────────────────────────────────────────────────┐
   │   shared memory.  zero leaks.  provable.  — GOVhence MEM-Ø  │
   └────────────────────────────────────────────────────────────┘
```

> **Naming:** written **GOVhence MEM-Ø** (the slashed Ø evokes zero-trust); typed as `MEM-0` in code,
> CLI, and filenames. The submission folder stays `team-one` per the hackathon's lowercase-hyphenated
> rule.
>
> **No secrets committed.** Real config stays local (`.env.example` documents the variables).
> The audit log here holds **only fake demo data**.
