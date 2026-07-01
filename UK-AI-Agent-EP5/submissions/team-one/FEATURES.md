# GOVhence MEM-Ø — Feature Datasheet

**Governed memory for shared AI agents** — one shared memory, zero leaks, provable to auditors.

## Implemented (live, 106 automated tests on branch `feat/govhence-pipeline`; 79 on `main`)
- **Live GOVhence pipeline** *(branch)* — end-to-end: classify → tag-relevance pre-filter → **deterministic
  bouncer access gate (audited)** → top-k MemoryLane → Responder; write path Judge → Memoriser → store.
  The LLM roles are deterministic stubs behind a clean seam (swap in an open-weight model later);
  **relevance never bypasses access** and no LLM is in the decision.
- **Deterministic access control** — strict exact-match category check; no AI in the decision.
- **Fail-closed by default** — any unknown/malformed/error case denies; never grants by accident.
- **Adversarial-hardened** — survives wrong types, look-alike Unicode, empty profiles (no leak, no crash).
- **Role-based permissions** — external editable config; allow / deny / "all-except" wildcard.
- **Self-checking config** — unknown user/role, typo'd category, or corrupt file → clear error.
- **Lineage revocation** — revoke a source → propagates to every derived item; "revoked beats allowed".
- **Regulator-grade audit log** — every ALLOW & DENY logged: who · what · when (UTC) · outcome · why.
- **Append-only, complete record** — no sampling, ever; full "who saw what, when" traceability.
- **Tamper-evident** — sequence numbers + SHA-256 hash chain; `verify()` detects any edit/delete/reorder.
- **Checkpoint / running-tally** — records (entry-count + head-hash) after every write: keeps appends **O(1)** (fast at any log size) **and** detects **end-truncation** (rows shaved off the tail) that a plain chain can't. Same pattern as Certificate Transparency / AWS CloudTrail / QLDB.
- **Self-sealing checkpoint** — the tally is itself an append-only SHA-256 chain (the CloudTrail "digest" trick): the tamper-detector is itself tamper-evident.
- **External anchor (mini)** — the latest tally is mirrored to a separate off-host file and cross-checked by `verify()` — the first concrete step of full external anchoring (roadmap → Kaspa).
- **No log → no access** — an access that can't be recorded is refused.
- **Total audit write (fail-closed on adversarial values)** *(R2)* — an oversized field or an unpaired
  Unicode surrogate can no longer crash the writer or brick the log; every value is made encode-safe +
  length-capped, and any residual write failure raises `AuditError` (access refused, never unlogged).
- **Injection-safe log** — spreadsheet-formula and row-forgery resistant.
- **Open-weight only · Python stdlib core** — minimal dependencies; portable.

## On the roadmap
- **Crypto-chain certification** — signed/non-repudiable records + external anchoring (e.g. Kaspa).
- **Police agent** — continuous security/rules monitor (alerts, never decides access).
- **Whistle-blower agent** — independent crypto-chained anomaly log; the message survives the messenger.
- **Whitehat agent** — live in-production red-team; behaves as normal user + attacker, leaves
  crypto-chained proof-of-presence "RFID taps" so skipped/silenced rounds are detectable.
- **Robustness + demo generator** — randomised users/queries (innocent errors + injection attempts);
  stress-test scale (must hold, zero false negatives) and human-readable demo scale.
- **Modern GUI** — staged pipeline visual: login → profile/RBAC → LLM uses shared memory → Scribe
  tags it → AI reads with limited access → access-check signal.
- **Scribe** — the write-time agent that classifies content and tags memory (labels only, never decides).
- **Size/length tripwire** — cheap per-unit length metadata flags possible leaks (no costly re-hash/LLM).
- **Tag-scoping discipline** — govern at the chunk/record level; tag in trusted metadata (not in body);
  untagged = deny; pre-filter vectors before return.
- **Scale & sync** — sub-200ms permission checks; live sync with external source ACLs.
