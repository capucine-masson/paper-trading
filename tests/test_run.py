from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from agent import run
from agent.broker import BrokerError
from agent.store import is_simulation

NOW = datetime(2026, 11, 16, 15, 7, tzinfo=UTC)


def test_executed_cycle_id_is_the_utc_hour() -> None:
    assert run.default_cycle_id(True, NOW) == "20261116T15"


def test_simulated_cycle_id_is_marked() -> None:
    cycle_id = run.default_cycle_id(False, NOW)
    assert cycle_id == "sim-20261116T15" and is_simulation(cycle_id)


def test_orders_cannot_be_sent_with_the_market_clock_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["run", "--execute", "--ignore-market-clock"])
    with pytest.raises(SystemExit):
        run._parse_args()


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--cycle-id", "20261116T15"],
        ["run", "--execute", "--cycle-id", "sim-20261116T15"],
    ],
)
def test_cycle_id_must_match_the_mode(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit):
        run._parse_args()


def test_unreachable_broker_at_startup_is_a_clean_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unreachable(*_: object) -> None:
        raise BrokerError("Alpaca request failed")

    monkeypatch.setattr("sys.argv", ["run"])
    monkeypatch.setattr(run, "load_secrets", lambda: None)
    monkeypatch.setattr(run, "Broker", unreachable)
    assert run.main() == run.EXIT_STARTUP_ERROR
    assert "Startup error: Alpaca request failed" in capsys.readouterr().err


def test_failing_cycle_exits_with_the_retryable_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailingCycle:
        def __init__(self, **_: object) -> None: ...

        def run(self) -> None:
            raise RuntimeError("boom")

    secrets = SimpleNamespace(fred_api_key=SecretStr(""))
    monkeypatch.setattr("sys.argv", ["run"])
    config = SimpleNamespace(market=SimpleNamespace(feed=""), broker=None, llm=None)
    monkeypatch.setattr(run, "load_config", lambda: config)
    monkeypatch.setattr(run, "load_secrets", lambda: secrets)
    monkeypatch.setattr(run, "Broker", lambda *_: None)
    monkeypatch.setattr(run, "make_client", lambda *_: None)
    monkeypatch.setattr(run, "JOURNAL_PATH", tmp_path / "journal.db")
    monkeypatch.setattr(run, "Cycle", FailingCycle)
    assert run.main() == run.EXIT_CYCLE_ERROR
