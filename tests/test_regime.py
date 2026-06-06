"""阶段 2 市场状态测试：纯分类函数 + 识别器（合成数据，不触网）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("pandas")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpharadar.regime.detector import (  # noqa: E402
    RegimeState, RegimeDetector,
    classify_trend, classify_style, classify_risk_appetite, classify_liquidity,
)


def _series(values, start="2022-01-03"):
    dates = pd.bdate_range(start=start, periods=len(values))
    return pd.Series(values, index=dates, dtype=float)


def _long_bars(symbol, values, start="2022-01-03"):
    dates = pd.bdate_range(start=start, periods=len(values))
    return pd.DataFrame({"symbol": symbol, "date": dates, "close": values})


# ── 趋势 ──────────────────────────────────────────────────────
def test_trend_bull():
    close = _series(np.linspace(100, 200, 260))  # 持续上行
    assert classify_trend(close, ma_window=200) == "bull"


def test_trend_bear():
    close = _series(np.linspace(200, 100, 260))  # 持续下行
    assert classify_trend(close, ma_window=200) == "bear"


def test_trend_range():
    rng = np.random.default_rng(0)
    close = _series(100 + rng.normal(0, 1, 260))  # 横盘震荡
    assert classify_trend(close, ma_window=200) == "range"


def test_trend_short_history_does_not_crash():
    assert classify_trend(_series([100, 101, 102]), ma_window=200) in {"bull", "range", "bear"}


# ── 风格 ──────────────────────────────────────────────────────
def test_style_growth():
    growth = _series(np.linspace(100, 130, 120))   # 成长跑赢
    value = _series(np.linspace(100, 105, 120))
    assert classify_style(growth, value) == "growth"


def test_style_value():
    growth = _series(np.linspace(100, 102, 120))
    value = _series(np.linspace(100, 125, 120))    # 价值跑赢
    assert classify_style(growth, value) == "value"


def test_style_balanced():
    both = _series(np.linspace(100, 120, 120))
    assert classify_style(both, both.copy()) == "balanced"


# ── 风险偏好 ──────────────────────────────────────────────────
def test_risk_high_when_small_leads():
    small = _series(np.linspace(100, 130, 120))
    large = _series(np.linspace(100, 103, 120))
    assert classify_risk_appetite(small, large) == "high"


def test_risk_low_when_small_lags():
    small = _series(np.linspace(100, 101, 120))
    large = _series(np.linspace(100, 125, 120))
    assert classify_risk_appetite(small, large) == "low"


# ── 流动性（无宏观数据时降级）────────────────────────────────
def test_liquidity_defaults_neutral():
    assert classify_liquidity(None, "2024-01-01") == "neutral"
    assert classify_liquidity(pd.DataFrame(), "2024-01-01") == "neutral"


# ── 识别器整合 ────────────────────────────────────────────────
def test_detector_assembles_state():
    n = 260
    # 宽基上行 → bull；成长跑赢价值 → growth；小盘跑赢大盘 → high
    bars = pd.concat([
        _long_bars("000300.SH", np.linspace(100, 180, n)),   # broad
        _long_bars("399006.SZ", np.linspace(100, 160, n)),   # growth
        _long_bars("000016.SH", np.linspace(100, 110, n)),   # value & large
        _long_bars("000852.SH", np.linspace(100, 150, n)),   # small
    ], ignore_index=True)

    detector = RegimeDetector(trend_ma_window=200, smoothing_days=5)
    state = detector.detect(bars)

    assert isinstance(state, RegimeState)
    assert state.trend == "bull"
    assert state.style == "growth"
    assert state.risk_appetite == "high"
    assert state.liquidity == "neutral"   # 未接宏观
    assert state.key() == "bull|growth|high"
    # 应满足 AI 光模块主线的市场状态触发条件
    assert state.matches({"style": ["growth", "balanced"], "risk_appetite": ["high", "neutral"]})


def test_detector_degrades_with_only_broad():
    bars = _long_bars("000300.SH", np.linspace(100, 180, 260))
    state = RegimeDetector().detect(bars)
    assert state.trend == "bull"
    assert state.style == "balanced"      # 无成长/价值指数 → 降级
    assert state.risk_appetite == "neutral"
