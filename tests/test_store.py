from pathlib import Path

from agent.store import Store

HOSTILE = "SPY'; DROP TABLE steps;--"


def test_step_round_trip(tmp_path: Path) -> None:
    store = Store(tmp_path / "j.db")
    assert store.get_step("c1", "SPY", "llm") is None
    store.save_step("c1", "SPY", "llm", '{"a": 1}')
    assert store.get_step("c1", "SPY", "llm") == '{"a": 1}'
    assert store.get_step("c2", "SPY", "llm") is None


def test_state_is_set_once_and_deletable(tmp_path: Path) -> None:
    store = Store(tmp_path / "j.db")
    assert store.get_or_set_state("k", "1") == "1"
    assert store.get_or_set_state("k", "2") == "1"
    store.delete_state("k")
    assert store.get_state("k") is None


def test_hostile_text_is_stored_verbatim(tmp_path: Path) -> None:
    store = Store(tmp_path / "j.db")
    store.save_step("c", HOSTILE, "x", "ok")
    assert store.get_step("c", HOSTILE, "x") == "ok"


def test_update_step_keeps_the_timestamp(tmp_path: Path) -> None:
    store = Store(tmp_path / "j.db")
    store.save_step("c", "SPY", "order", "old")
    created = store.list_steps("order")[0].created_at
    store.update_step("c", "SPY", "order", "new")
    row = store.list_steps("order")[0]
    assert row.result == "new" and row.created_at == created
