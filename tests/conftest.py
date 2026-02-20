import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from otterai import config


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory for testing."""
    env_patch = {"OTTERAI_USERNAME": "", "OTTERAI_PASSWORD": ""}
    with patch.dict(os.environ, env_patch, clear=False):
        os.environ.pop("OTTERAI_USERNAME", None)
        os.environ.pop("OTTERAI_PASSWORD", None)
        with patch.object(config, "CONFIG_DIR", tmp_path):
            with patch.object(config, "CONFIG_FILE", tmp_path / "config.json"):
                yield tmp_path
