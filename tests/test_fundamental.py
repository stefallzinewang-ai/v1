"""阶段 3 测试：因子标准化/合成/动量 + 公司基本面打分（合成数据，不触网）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("pandas")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpharadar.factors.library import (  # noqa: E402
    standardize, cross_section_score, compute_momentum,
)
from alpharadar.fundamental.scorer import FundamentalScorer  # noqa: E402


# ── 标准化 ────────────────────────────────────────────────────
def test_standardize_zscore():
    out = standardize(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert abs(out.mean()) < 1e-9              # 均值约 0
    assert out.iloc[-1] > out.iloc[0]          # 保序


def test_standardize_direction_down():
    # 越小越好（如估值）：最小值应得最高分
    out = standardize(pd.Series([10.0, 20.0, 30.0]), direction="down")
    assert out.iloc[0] > out.iloc[-1]


def test_standardize_rank_in_unit_interval():
    out = standardize(pd.Series([5.0, 1.0, 3.0]), method="rank")
    assert out.between(0, 1).all()
    assert out.idxmax() == 0  # 最大值 rank 最高


def test_standardize_handles_nan_and_constant():
    assert (standardize(pd.Series([np.nan, np.nan])) == 0).all()
    assert (standardize(pd.Series([3.0, 3.0, 3.0])) == 0).all()


def test_cross_section_score_weights():
    a = pd.Series({"x": 1.0, "y": 0.0})
    b = pd.Series({"x": 0.0, "y": 1.0})
    out = cross_section_score({"a": a, "b": b}, weights={"a": 3.0, "b": 1.0})
    assert out["x"] > out["y"]   # a 权重更大，x 占优


def test_compute_momentum():
    dates = pd.bdate_range("2024-01-02", periods=70)
    up = pd.DataFrame({"symbol": "A", "date": dates, "close": np.linspace(100, 200, 70)})
    flat = pd.DataFrame({"symbol": "B", "date": dates, "close": np.full(70, 100.0)})
    mom = compute_momentum(pd.concat([up, flat]), as_of=dates[-1], lookback=63)
    assert mom["A"] > 0 and abs(mom["B"]) < 1e-9


# ── 基本面打分：point-in-time ──────────────────────────────────
def _financials():
    """两只股票，各两期；含公告日。A 成长更强、质量更高。"""
    return pd.DataFrame([
        # symbol, report_period, ann_date, rev, rev_yoy, np, np_yoy, gm, roe, ocf
        ("300308.SZ", "2023-12-31", "2024-04-15", 100, 10, 20, 30, 30.0, 15.0, 1.0),
        ("300308.SZ", "2024-03-31", "2024-04-25", 50, 80, 9, 250, 33.0, 7.0, 0.5),
        ("300502.SZ", "2023-12-31", "2024-04-10", 80, 5, 10, 5, 22.0, 8.0, 0.3),
        ("300502.SZ", "2024-03-31", "2024-04-28", 40, 12, 4, 20, 23.0, 4.0, 0.2),
    ], columns=["symbol", "report_period", "ann_date", "revenue", "revenue_yoy",
                "net_profit", "net_profit_yoy", "gross_margin", "roe", "ocf"])


def test_latest_pit_respects_ann_date():
    fin = _financials()
    scorer = FundamentalScorer()
    # 截至 2024-04-20：300308 只有年报(04-15)可用，一季报(04-25)还没公告
    pit = scorer.latest_pit(fin, as_of="2024-04-20")
    assert str(pit.loc["300308.SZ", "report_period"].date()) == "2023-12-31"
    assert pit.loc["300308.SZ", "net_profit_yoy"] == 30


def test_latest_pit_acceleration():
    fin = _financials()
    pit = FundamentalScorer().latest_pit(fin, as_of="2024-05-01")
    # 截至 5-1：取一季报，加速度 = 250 - 30 = 220
    assert str(pit.loc["300308.SZ", "report_period"].date()) == "2024-03-31"
    assert pit.loc["300308.SZ", "net_profit_accel"] == 220


def test_score_ranks_stronger_company_first():
    fin = _financials()
    result = FundamentalScorer().score(fin, as_of="2024-05-01")
    assert list(result.columns) == ["report_period", "ann_date", "growth", "quality", "total"]
    # A(300308) 成长与质量都更强 → 排第一
    assert result.index[0] == "300308.SZ"
    assert result.loc["300308.SZ", "growth"] > result.loc["300502.SZ", "growth"]
    assert result.loc["300308.SZ", "quality"] > result.loc["300502.SZ", "quality"]


def test_score_empty_input():
    empty = pd.DataFrame(columns=_financials().columns)
    assert FundamentalScorer().score(empty, as_of="2024-05-01").empty


def test_emphasis_weights_applied():
    fin = _financials()
    # 极端偏重质量；A 质量更高，应仍排第一
    scorer = FundamentalScorer(emphasis={"growth": 0.0, "quality": 1.0})
    result = scorer.score(fin, as_of="2024-05-01")
    assert result.index[0] == "300308.SZ"
