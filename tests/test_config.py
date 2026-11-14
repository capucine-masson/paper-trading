from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.config import CONFIG_PATH, load_config


def test_repository_config_is_valid() -> None:
    assert load_config(CONFIG_PATH).market.symbols[0] == "SPY"


def test_invalid_value_is_rejected(tmp_path: Path) -> None:
    text = CONFIG_PATH.read_text().replace("horizon = 6", "horizon = 0")
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ValidationError):
        load_config(path)
