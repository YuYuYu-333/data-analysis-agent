"""配置模块：必需项校验与默认值。"""

import pytest

import app.config as config


def test_required_values_are_loaded():
    assert config.DEEPSEEK_API_KEY
    assert config.SILICONFLOW_API_KEY


def test_required_rejects_empty():
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        config._require("DEEPSEEK_API_KEY", None)
