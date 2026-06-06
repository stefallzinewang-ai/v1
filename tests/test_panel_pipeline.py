"""阶段 5 整合测试：训练面板构建 + 规律库接入 run 流水线（合成数据，不触网）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")
pytest.importorskip("yaml")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpharadar.data.store import DataStore  # noqa: E402
from alpharadar.regime.detector import RegimeDetector  # noqa: E402
from alpharadar.mining.panel import build_training_panel, price_factors  # noqa: E402
from alpharadar.mining.pattern_miner import PatternMiner, PatternLibrary, Pattern  # noqa: E402


def _bars(sym, vals, start="2021-01-04"):
    d = pd.bdate_range(start, periods=len(vals))
    return pd.DataFrame({"symbol": sym, "date": d, "open": vals, "high": vals,
                         "low": vals, "close": vals, "volume": 1.0, "amount": 1.0,
                         "turnover": 0.1})


def test_price_factors_shapes():
    close = pd.DataFrame({"A": np.linspace(100, 200, 300),
                          "B": np.linspace(100, 90, 300)},
                         index=pd.bdate_range("2021-01-04", periods=300))
    facs = price_factors(close)
    assert set(facs) == {"mom_63", "mom_252", "reversal_5", "vol_21"}
    assert facs["mom_63"].shape == close.shape


def test_build_training_panel_structure():
    n = 400
    universe = pd.concat([_bars(f"{600000+i}.SH",
                                np.linspace(100, 100 + i, n)) for i in range(8)],
                         ignore_index=True)
    index_bars = pd.concat([
        _bars("000300.SH", np.linspace(100, 160, n)),
        _bars("399006.SZ", np.linspace(100, 150, n)),
        _bars("000016.SH", np.linspace(100, 110, n)),
        _bars("000852.SH", np.linspace(100, 140, n)),
    ], ignore_index=True)
    detector = RegimeDetector()
    panel, regimes, fwd = build_training_panel(universe, index_bars, detector,
                                               forward_days=21, min_history=120)
    assert not panel.empty and not fwd.empty
    assert {"date", "symbol"}.issubset(panel.columns)
    assert "mom_63" in panel.columns
    assert "fwd_ret" in fwd.columns
    assert "regime_key" in regimes.columns
    # 训练器能消费这三张表
    lib = PatternMiner(forward_days=21, min_obs=10).fit(panel, regimes, fwd)
    assert isinstance(lib, PatternLibrary)


def test_pattern_library_integration_in_pipeline(tmp_path):
    """放一个规律库到 store，run 流水线应在候选 breakdown 里出现「规律信号」alpha。"""
    from alpharadar.config import Settings
    from alpharadar.pipeline import run_pipeline

    store = DataStore(root=tmp_path)
    n = 260
    store.write_bars(pd.concat([
        _bars("000300.SH", np.linspace(100, 180, n)),
        _bars("399006.SZ", np.linspace(100, 160, n)),
        _bars("000016.SH", np.linspace(100, 108, n)),
        _bars("000852.SH", np.linspace(100, 150, n)),
        _bars("300308.SZ", np.linspace(100, 200, n)),
        _bars("300502.SZ", np.linspace(100, 130, n)),
        _bars("300394.SZ", np.linspace(100, 110, n)),
    ], ignore_index=True))
    fin = pd.DataFrame([
        ("300308.SZ", "2021-03-31", "2021-04-25", 50, 80, 9, 250, 33.0, 7.0, 0.5),
        ("300502.SZ", "2021-03-31", "2021-04-28", 40, 12, 4, 20, 23.0, 4.0, 0.2),
        ("300394.SZ", "2021-03-31", "2021-04-22", 30, 8, 3, 10, 25.0, 6.0, 0.2),
    ], columns=["symbol", "report_period", "ann_date", "revenue", "revenue_yoy",
                "net_profit", "net_profit_yoy", "gross_margin", "roe", "ocf"])
    store.write_table("financials", fin, subset=["symbol", "report_period"])

    # 放一个针对当前状态(bull|growth|high)的规律库
    PatternLibrary({"bull|growth|high": Pattern(
        regime_key="bull|growth|high",
        weights={"mom_63": 0.6, "mom_252": 0.3, "reversal_5": -0.05, "vol_21": -0.05},
        in_sample_ic=0.2, out_sample_ic=0.1, n_obs=200)
    }).save(Path(tmp_path) / "patterns.json")

    settings = Settings(raw={"storage": {"root": str(tmp_path)}, "selection": {"top_n": 2}})
    result = run_pipeline("ai_optical_module", as_of="2021-12-31", settings=settings)
    assert result.candidates
    # 规律信号维度应进入打分明细
    assert "alpha" in result.candidates[0].breakdown
    assert "规律信号" in result.report
