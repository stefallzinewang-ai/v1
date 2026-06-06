"""阶段 6/8 测试：选股融合 + 报告 + 端到端流水线（合成数据，不触网）。"""
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

from alpharadar.selection.selector import Selector, Candidate  # noqa: E402
from alpharadar.report.builder import ReportBuilder  # noqa: E402
from alpharadar.regime.detector import RegimeState  # noqa: E402
from alpharadar.theme.chain import ThemeActivation  # noqa: E402


# ── 选股融合 ──────────────────────────────────────────────────
def test_selector_ranks_and_truncates():
    dims = {
        "growth": pd.Series({"A": 1.0, "B": 0.0, "C": -1.0}),
        "quality": pd.Series({"A": 0.5, "B": 0.0, "C": -0.5}),
    }
    cands = Selector(top_n=2).select(dims, weights={"growth": 0.7, "quality": 0.3})
    assert [c.symbol for c in cands] == ["A", "B"]   # 取 Top 2，A 最高
    assert isinstance(cands[0], Candidate)
    assert cands[0].breakdown["growth"] == 1.0


def test_selector_weights_change_order():
    dims = {
        "growth": pd.Series({"A": 1.0, "B": -1.0}),
        "momentum": pd.Series({"A": -1.0, "B": 1.0}),
    }
    # 偏重动量 → B 胜出
    cands = Selector(top_n=1).select(dims, weights={"growth": 0.1, "momentum": 0.9})
    assert cands[0].symbol == "B"


def test_selector_reasons_sorted_by_contribution():
    dims = {"growth": pd.Series({"A": 1.0}), "quality": pd.Series({"A": -1.0})}
    cands = Selector().select(dims, weights={"growth": 0.8, "quality": 0.2})
    # 成长贡献为正且权重大 → 排在理由首位，并标「优势」
    assert "成长" in cands[0].reasons[0] and "优势" in cands[0].reasons[0]


def test_selector_empty():
    assert Selector().select({}) == []


# ── 报告 ──────────────────────────────────────────────────────
def test_report_contains_chain():
    regime = RegimeState("bull", "growth", "high", "neutral", "2025-06-30")
    act = ThemeActivation(active=True, reasons=["✓ 政策支持：人工智能产业政策"])
    cand = Candidate(symbol="300308.SZ", name="中际旭创", total_score=1.2,
                     breakdown={"growth": 1.0, "quality": 0.8}, reasons=["成长 +1.00（优势）"],
                     report_period="2025-03-31")
    md = ReportBuilder().build(
        theme_name="AI 算力 · 光模块", as_of="2025-06-30", regime=regime,
        activation=act, bottleneck={"name": "光模块", "note": "传输瓶颈"},
        key_variables=[{"name": "传输速率代际", "metric": "800G 渗透率"}],
        candidates=[cand])
    assert "市场状态" in md and "bull|growth|high" in md
    assert "光模块" in md
    assert "中际旭创" in md and "300308.SZ" in md
    assert "不构成任何投资建议" in md


def test_report_handles_no_candidates():
    md = ReportBuilder().build(
        theme_name="X", as_of="2025-01-01", regime=None, activation=None,
        bottleneck=None, key_variables=None, candidates=[])
    assert "无可用数据" in md


# ── 端到端流水线 ──────────────────────────────────────────────
def _seed_store(root):
    from alpharadar.data.store import DataStore

    store = DataStore(root=root)
    n = 260
    dates = pd.bdate_range("2024-01-02", periods=n)

    def bars(sym, vals):
        return pd.DataFrame({"symbol": sym, "date": dates, "open": vals, "high": vals,
                             "low": vals, "close": vals, "volume": 1.0, "amount": 1.0,
                             "turnover": 0.1})

    # 指数：bull|growth|high
    store.write_bars(pd.concat([
        bars("000300.SH", np.linspace(100, 180, n)),
        bars("399006.SZ", np.linspace(100, 160, n)),
        bars("000016.SH", np.linspace(100, 108, n)),
        bars("000852.SH", np.linspace(100, 150, n)),
        # 候选股行情（动量）
        bars("300308.SZ", np.linspace(100, 200, n)),
        bars("300502.SZ", np.linspace(100, 130, n)),
        bars("300394.SZ", np.linspace(100, 110, n)),
    ], ignore_index=True))

    fin = pd.DataFrame([
        ("300308.SZ", "2024-03-31", "2024-04-25", 50, 80, 9, 250, 33.0, 7.0, 0.5),
        ("300308.SZ", "2023-12-31", "2024-04-15", 100, 10, 20, 30, 30.0, 15.0, 1.0),
        ("300502.SZ", "2024-03-31", "2024-04-28", 40, 12, 4, 20, 23.0, 4.0, 0.2),
        ("300502.SZ", "2023-12-31", "2024-04-10", 80, 5, 10, 5, 22.0, 8.0, 0.3),
        ("300394.SZ", "2024-03-31", "2024-04-22", 30, 8, 3, 10, 25.0, 6.0, 0.2),
        ("300394.SZ", "2023-12-31", "2024-04-12", 60, 6, 8, 8, 24.0, 7.0, 0.3),
    ], columns=["symbol", "report_period", "ann_date", "revenue", "revenue_yoy",
                "net_profit", "net_profit_yoy", "gross_margin", "roe", "ocf"])
    store.write_table("financials", fin, subset=["symbol", "report_period"])


def test_pipeline_end_to_end(tmp_path):
    from alpharadar.config import Settings
    from alpharadar.pipeline import run_pipeline

    _seed_store(tmp_path)
    settings = Settings(raw={"storage": {"root": str(tmp_path)},
                             "selection": {"top_n": 2}})
    result = run_pipeline("ai_optical_module", as_of="2024-12-31", settings=settings)

    assert result.regime is not None and result.regime.key() == "bull|growth|high"
    assert result.activation is not None and result.activation.active is True
    assert len(result.candidates) == 2          # Top 2
    assert result.candidates[0].symbol == "300308.SZ"   # 成长+质量+动量都最强
    assert "中际旭创" in result.report
    assert "不构成任何投资建议" in result.report
