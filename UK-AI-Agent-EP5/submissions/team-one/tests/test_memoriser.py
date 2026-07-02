"""Tests for the Memoriser — the write-time labeller AND the store's only writer.

Deterministic tests inject a FAKE llm (no network) to verify the guardrails:
FAIL-CLOSED writes (offline/junk/invalid/disk-failure -> refused, store untouched),
the WRITER CAP (labels must sit within the writer's own clearances), and
PERSISTENCE (accepted memories survive a restart — written atomically to a runtime
store seeded from the committed seed). One live smoke test calls the real model,
skipped if no key is configured.

Every test passes store_path= a TEMP path so the real data/cocoshamem.json is
never touched (project rule: tests never write real runtime artifacts).
"""
import json

import pytest

import bouncer
import llm
import memoriser

# self-contained profile store: ben holds {shared, logistics}; max holds all three.
USERS = {
    "roles": {
        "driver":  {"department": "logistics",  "clearances": ["shared", "logistics"]},
        "auditor": {"department": "compliance", "clearances": ["shared", "financials", "legal"]},
    },
    "users": {"ben": "driver", "max": "auditor"},
}


@pytest.fixture
def users_path(tmp_path):
    p = tmp_path / "users.json"
    p.write_text(json.dumps(USERS), encoding="utf-8")
    return p


@pytest.fixture
def store(tmp_path):
    """A TEMP runtime-store path (does not exist yet) — keeps every test off the
    real data/cocoshamem.json."""
    return tmp_path / "cocoshamem.json"


def _fake(reply):
    def _chat(system, user, **kw):
        return reply
    return _chat


# --- happy path -------------------------------------------------------------------

def test_stores_with_llm_labels(users_path, store):
    mem = []
    ack = memoriser.memorise("Depot closes early on Fridays", ["depot", "schedule", "depot"],
                             mem, "ben", users_path=users_path,
                             chat=_fake('{"security_labels": ["logistics"]}'), store_path=store)
    assert ack.startswith("stored")
    assert len(mem) == 1
    assert mem[0]["labels"] == ["logistics"]
    assert mem[0]["topics"] == ["depot", "schedule"]          # deduped, order kept
    assert mem[0]["text"] == "Depot closes early on Fridays"  # verbatim, no expansion


def test_multiple_labels_all_kept_most_restrictive(users_path, store):
    # max holds financials+legal; both labels stick -> readers must hold BOTH.
    mem = []
    memoriser.memorise("Acme settled for 250k", ["settlement"], mem, "max",
                       users_path=users_path,
                       chat=_fake('{"security_labels": ["financials", "legal"]}'),
                       store_path=store)
    assert mem[0]["labels"] == ["financials", "legal"]


# --- persistence: the Memoriser is the store's only writer -------------------------

def test_persists_to_runtime_store_seeded_from_seed(users_path, store, tmp_path):
    # First write COPIES the committed seed into the runtime store, then appends.
    seed = tmp_path / "cocoshamem.seed.json"
    seed.write_text(json.dumps({"memories": [
        {"labels": ["shared"], "topics": ["parking"], "text": "seeded memory"}]}),
        encoding="utf-8")
    mem = []
    ack = memoriser.memorise("Depot closes at 9pm Fridays", ["depot"], mem, "ben",
                             users_path=users_path,
                             chat=_fake('{"security_labels": ["logistics"]}'),
                             store_path=store, seed_path=seed)
    assert ack.startswith("stored")
    stored = json.loads(store.read_text(encoding="utf-8"))["memories"]
    assert [m["text"] for m in stored] == ["seeded memory", "Depot closes at 9pm Fridays"]
    # the seed file itself is never modified
    assert len(json.loads(seed.read_text(encoding="utf-8"))["memories"]) == 1


def test_teach_restart_recall(users_path, store):
    # THE point of a memory system: what ben teaches survives a process restart.
    memoriser.memorise("The Watford depot closes at 9pm on Fridays", ["depot", "schedule"],
                       [], "ben", users_path=users_path,
                       chat=_fake('{"security_labels": ["logistics"]}'), store_path=store)
    # "restart": a FRESH load from disk (no shared in-RAM list), then retrieval.
    reloaded = bouncer.load_memories(store)
    lane = bouncer.retrieve(["depot"], "ben", reloaded, users_path=users_path)
    assert [m["text"] for m in lane] == ["The Watford depot closes at 9pm on Fridays"]


def test_disk_failure_refused_ram_untouched(users_path, tmp_path):
    # Unwritable store path (missing directory) -> refused, list untouched, no file.
    bad_store = tmp_path / "no_such_dir" / "cocoshamem.json"
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"security_labels": ["shared"]}'),
                             store_path=bad_store)
    assert ack.startswith("NOT stored") and "fail-closed" in ack
    assert mem == [] and not bad_store.exists()


def test_corrupt_existing_store_refused(users_path, store):
    store.write_text("{ not json", encoding="utf-8")
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"security_labels": ["shared"]}'), store_path=store)
    assert ack.startswith("NOT stored") and mem == []
    assert store.read_text(encoding="utf-8") == "{ not json"   # untouched, not clobbered


# --- the WRITER CAP (labels only) --------------------------------------------------

def test_label_above_writer_clearance_is_refused(users_path, store):
    # ben (driver) writes something the labeller calls financials -> refused.
    mem = []
    ack = memoriser.memorise("Q3 revenue was 4.2M", ["revenue"], mem, "ben",
                             users_path=users_path,
                             chat=_fake('{"security_labels": ["financials"]}'),
                             store_path=store)
    assert ack.startswith("NOT stored") and "above the writer's clearance" in ack
    assert mem == [] and not store.exists()                   # store untouched


def test_unknown_writer_cannot_store_anything(users_path, store):
    mem = []
    ack = memoriser.memorise("anything", ["x"], mem, "mallory",
                             users_path=users_path, chat=_fake('{"security_labels": ["shared"]}'),
                             store_path=store)
    assert ack.startswith("NOT stored") and mem == []         # no clearances -> no cap passes


# --- vocabulary + validity (strict, fail-closed) -----------------------------------

def test_label_outside_vocabulary_is_refused(users_path, store):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"security_labels": ["topsecret"]}'), store_path=store)
    assert ack.startswith("NOT stored") and "vocabulary" in ack and mem == []


def test_label_case_mismatch_is_refused(users_path, store):
    # strict exact strings: 'Logistics' is NOT the label 'logistics'.
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"security_labels": ["Logistics"]}'), store_path=store)
    assert ack.startswith("NOT stored") and mem == []


def test_empty_labels_refused(users_path, store):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"security_labels": []}'), store_path=store)
    assert ack.startswith("NOT stored") and mem == []


def test_non_list_labels_refused(users_path, store):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake('{"security_labels": "shared"}'), store_path=store)
    assert ack.startswith("NOT stored") and mem == []


# --- fail-closed writes: offline / junk never store --------------------------------

def test_junk_json_refused_not_crash(users_path, store):
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path,
                             chat=_fake("not json at all"), store_path=store)
    assert ack.startswith("NOT stored") and "fail-closed" in ack and mem == []


def test_llm_offline_refused_not_crash(users_path, store):
    def boom(system, user, **kw):
        raise llm.LLMError("model offline")
    mem = []
    ack = memoriser.memorise("m", ["x"], mem, "ben", users_path=users_path, chat=boom,
                             store_path=store)
    assert ack.startswith("NOT stored") and mem == []


# --- prompt & routing --------------------------------------------------------------

def test_routes_to_MEMORISER_component_and_prompt_content(users_path, store):
    seen = {}

    def rec(system, user, **kw):
        seen["component"] = kw.get("component")
        seen["user"] = user
        return '{"security_labels": ["shared"]}'

    memoriser.memorise("bread news", ["bread"], [], "ben", users_path=users_path, chat=rec,
                       store_path=store)
    assert seen["component"] == "MEMORISER"
    assert "financials" in seen["user"]           # FULL vocabulary offered (cap is in code)
    assert "role=driver" in seen["user"]          # role+dept context sent...
    assert "ben" not in seen["user"]              # ...but NEVER the writer's name


def test_llm_facing_text_says_security_label_never_memory(users_path, store):
    # Owner decision (2 Jul): LLM-facing text never says "memory" — a model reads that
    # as its OWN memory/chat history (even the role name MEMORISER is memory-flavoured,
    # so the prompt says "security labeller"). Bare "label" is ambiguous too: the prompt
    # says "security label" and the LLM JSON contract key is "security_labels".
    seen = {}

    def rec(system, user, **kw):
        seen["system"], seen["user"] = system, user
        return '{"security_labels": ["shared"]}'

    memoriser.memorise("bread news", ["bread"], [], "ben", users_path=users_path, chat=rec,
                       store_path=store)
    scaffolding = (seen["system"] + "\n" + seen["user"]).lower()
    assert "memor" not in scaffolding               # no memory/memories/memoriser
    assert "security label" in scaffolding          # the unambiguous term
    assert '"security_labels"' in seen["system"]    # the JSON contract uses it too


# --- live smoke: the real model (skipped without a key) ----------------------------

def _memoriser_configured():
    key = llm._config("MEMORISER")[2]
    return bool(key) and not key.startswith("your-")


@pytest.mark.skipif(not _memoriser_configured(), reason="no MEMORISER LLM key configured (.env)")
def test_live_memoriser_smoke(users_path, store):
    mem = []
    ack = memoriser.memorise("The Watford depot accepts deliveries until 2pm on Fridays.",
                             ["delivery", "depot"], mem, "ben", users_path=users_path,
                             store_path=store)
    # Whatever the model says, the deterministic guardrails hold:
    if mem:
        assert set(mem[0]["labels"]) <= {"shared", "logistics"}   # within ben's clearances
    else:
        assert ack.startswith("NOT stored")
