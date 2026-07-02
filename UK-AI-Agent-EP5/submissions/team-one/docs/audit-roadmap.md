# ToDo — Audit Log (security-first)

The audit log is a **regulatory record**: complete, immutable, timestamped, tamper-evident,
retained. There is **no "sample"** — every access decision is recorded, always.

## Best practices for our use case
1. **Log everything, every time** — every decision, ALLOW and DENY. No gaps, no sampling.
2. **Append-only** — only add rows; never edit or delete existing ones.  ✅ done
3. **Timestamp every row** in UTC (ISO-8601).  ✅ done
4. **Capture who / what / when / outcome / why** — user, item, timestamp, decision, reason.  ✅ done
5. **Tamper-evident** — add:
   - a **sequence number** per row (a deleted row leaves a visible gap);
   - a **hash chain** (each row stores a fingerprint of the previous row, so any edit,
     deletion, insertion, or reorder breaks the chain and is detectable).
6. **Durable writes** — flush each row to disk immediately so a crash can't lose the last record.
7. **Retain everything** for the full required period. If the file grows, split into **dated files
   that are all kept** — never delete to save space. If storage ever becomes a real concern,
   **ASK the user**, do not decide unilaterally.
8. **Integrity-check function** — a `verify()` that proves the log was not tampered with.

## Status
- Done: 1 (partial — coverage), 2, 3, 4.
- Next security upgrade: **5, 6, 8** — sequence number + hash chain + `verify()`, stdlib-only, tested.

## Research findings (cited: NIST 800-92, 800-53 AU family, ISO 27001 A.8.15/8.17, PCI-DSS v4, SEC 17a-4, FINTRAC)
- **CORRECTION:** FINTRAC retention is **5 years, not 7** (7yr is a tax/SOX figure). Plan: keep **7 years**
  as a safe superset of all rules (FINTRAC 5 / PCI 12mo / SEC 6yr), but cite it correctly.
- **Hash chain validated** as the standard tamper-evidence pattern (NIST AU-9(3) crypto integrity,
  AU-10 non-repudiation, SEC 17a-4 WORM-alternative, PCI 10.5 change-detection). Stdlib hashlib + csv.
- **Add fields:**
  - `event_type` (e.g. RETRIEVE) — standards require "what type of event"; future-proofs writes/deletes.
  - `user_location` + `item_jurisdiction` — satisfy the "where" field AND the cross-border bonus at once.
- **Enforce append-only in code** (open mode 'a' only; never 'w'/'r+'; no update/delete paths) and at the
  OS level at deployment (file ACL: app can append but not delete/edit; POSIX `chattr +a`).
- **Time:** keep UTC ISO-8601 with microseconds (NIST AU-8). Deployment note: host must run NTP/w32time
  (ISO A.8.17). The chain orders events by sequence, so integrity does not depend on clock monotonicity.
- **Anchoring confirmed:** a local chain can be wholly rewritten by an insider; fixing that needs the latest
  hash published OUTSIDE their control (separate append-only "anchor" file now; blockchain/Kaspa later).
  Anchor only the hash/Merkle root — never raw records.

## Open question — blockchain anchoring (e.g. Kaspa)?
Considering a blockchain for immutable certification + user identity. Notes / decision pending:
- A **local hash chain** (point 5) already gives strong tamper-evidence cheaply, offline, no deps.
  An insider *can* still rewrite the WHOLE chain locally, because they hold the data and the code.
- **Blockchain adds one specific thing**: external, independent proof that the log existed and was
  unchanged **as of a point in time** — an insider can't silently rewrite history because the proof
  lives outside their control. This is "anchoring/notarization".
- **Right pattern if we do it:** keep the full log local (off-chain); periodically publish only the
  **latest chain hash** (a Merkle root / digest) on-chain. NEVER put raw audit data on a public chain
  (privacy + cost). On-chain = a tiny fingerprint; off-chain = the real, complete record.
- Kaspa fit: fast, cheap, high-throughput PoW with frequent blocks → good for frequent anchoring;
  but adds a network dependency, a wallet (use a throwaway, never commit keys), and complexity.
- **Hackathon angle:** strong "innovation" + the prompt mentions web3/wallets, so it could score; but
  it is **upside**, not the core. Core security is met by the local hash chain.
- **User identity on-chain:** likely NOT needed/appropriate — identity should stay in the access
  layer; putting user identity on a public chain is a privacy risk. Revisit only with a clear reason.

### Decision
- [ ] Build local tamper-evidence first (points 5, 6, 8). REQUIRED, do now.
- [ ] THEN optionally add periodic hash-anchoring to a chain (Kaspa) as an upside feature — only the
      digest, never raw records. Decide after the core is solid.
