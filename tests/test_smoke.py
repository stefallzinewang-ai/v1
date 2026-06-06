"""冒烟测试：确认骨架可导入、配置可解析、CLI 可运行。

不依赖 akshare/pandas 等重依赖；仅校验架构骨架自洽。
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def test_package_imports():
    import alpharadar

    assert alpharadar.__version__


def test_layer_modules_import():
    # 八层关键模块均可被导入（接口骨架自洽）
    import alpharadar.regime  # noqa: F401
    import alpharadar.factors  # noqa: F401
    import alpharadar.mining  # noqa: F401
    import alpharadar.theme  # noqa: F401
    import alpharadar.fundamental  # noqa: F401
    import alpharadar.selection  # noqa: F401
    import alpharadar.backtest  # noqa: F401
    import alpharadar.report  # noqa: F401


def test_regime_state_matches():
    from alpharadar.regime import RegimeState

    state = RegimeState(
        trend="bull", style="growth", risk_appetite="high",
        liquidity="easing", as_of="2026-06-06",
    )
    assert state.matches({"style": ["growth", "balanced"]})
    assert not state.matches({"style": ["value"]})


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("yaml") is None,
    reason="需要 PyYAML 才能解析主线配置",
)
def test_example_theme_loads():
    from alpharadar.config import ThemeConfig, list_themes

    assert "ai_optical_module" in list_themes()
    theme = ThemeConfig.load("ai_optical_module")
    assert theme.name
    # 内置示例里光模块应被标为瓶颈环节
    bottleneck = theme.bottleneck_stage
    assert bottleneck is not None and "光模块" in bottleneck["name"]
    assert theme.seed_symbols  # 候选种子股非空


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "alpharadar.cli", "--help"],
        cwd=ROOT, env={"PYTHONPATH": str(SRC), "PATH": ""},
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "alpharadar" in result.stdout
