"""阶段 6b 测试：回测引擎（合成数据，不触网）。

构造一个 mom_63 能预测前瞻收益的世界，用对应 Pattern 回测，应跑赢等权基准。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("pandas")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpharadar.backtest.engine import BacktestEngine, BacktestResult, _max_drawdown  # noqa: E402
from alpharadar.mining.pattern_miner import PatternLibrary, Pattern  # noqa: E402


def _world(n_dates=60, n_symbols=40, seed=0, regime="bull|growth|high", signal=0.8):
    """mom_63 ~ 因子；fwd_ret = signal*mom_63 + 噪声。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates, freq="C")
    # 用月度日期，配合 stride 抽样
    dates = pd.date_range("2020-01-31", periods=n_dates, freq="ME")
    syms = [f"{600000 + i}.SH" for i in range(n_symbols)]
    prows, frows, rrows = [], [], []
    for d in dates:
        mom = rng.normal(0, 1, n_symbols)
        fwd = signal * mom + (1 - signal) * rng.normal(0, 1, n_symbols)
        fwd = fwd * 0.05  # 缩放到合理收益量级
        for s, m in zip(syms, mom):
            prows.append({"date": d, "symbol": s, "mom_63": m, "vol_21": rng.normal()})
        for s, f in zip(syms, fwd):
            frows.append({"date": d, "symbol": s, "fwd_ret": f})
        rrows.append({"date": d, "regime_key": regime})
    return pd.DataFrame(prows), pd.DataFrame(rrows), pd.DataFrame(frows)


def test_max_drawdown():
    eq = pd.Series([1.0, 1.2, 0.9, 1.1])
    assert _max_drawdown(eq) == pytest.approx(-0.25)   # 1.2→0.9


def test_backtest_beats_benchmark_with_good_pattern():
    panel, regime, fwd = _world(signal=0.85)
    lib = PatternLibrary({"bull|growth|high": Pattern(
        regime_key="bull|growth|high", weights={"mom_63": 1.0, "vol_21": 0.0})})
    res = BacktestEngine(top_k=5, forward_days=21).run(panel, regime, fwd, pattern_lib=lib)
    assert isinstance(res, BacktestResult)
    assert res.n_periods > 0
    assert res.annual_excess_return > 0      # 跑赢等权基准
    assert res.win_rate > 0.5                # 多数期跑赢
    assert res.equity_curve is not None and len(res.equity_curve) == res.n_periods


def test_backtest_no_edge_when_factor_useless():
    # 因子与收益无关（signal≈0）→ 超额应接近 0、不显著为正
    panel, regime, fwd = _world(signal=0.0, seed=3)
    lib = PatternLibrary({"bull|growth|high": Pattern(
        regime_key="bull|growth|high", weights={"mom_63": 1.0})})
    res = BacktestEngine(top_k=5, forward_days=21).run(panel, regime, fwd, pattern_lib=lib)
    assert res.n_periods > 0
    assert abs(res.annual_excess_return) < 0.15   # 没有稳定 edge

def test_backtest_default_baseline_runs():
    panel, regime, fwd = _world(signal=0.6)
    res = BacktestEngine(top_k=5, forward_days=21).run(panel, regime, fwd)  # 无 pattern → 默认动量
    assert res.n_periods > 0
    assert res.summary()


def test_backtest_empty_input():
    empty = pd.DataFrame(columns=["date", "symbol"])
    res = BacktestEngine().run(empty, pd.DataFrame(columns=["date", "regime_key"]),
                               pd.DataFrame(columns=["date", "symbol", "fwd_ret"]))
    assert res.n_periods == 0
