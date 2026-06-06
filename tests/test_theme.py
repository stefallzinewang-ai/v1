"""阶段 4 主线映射测试：激活判断 + 候选池解析（用真实示例配置，不触网）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("yaml")
pytest.importorskip("pandas")
import pandas as pd  # noqa: E402

from alpharadar.theme import ThemeEngine  # noqa: E402
from alpharadar.regime.detector import RegimeState  # noqa: E402


def _engine():
    return ThemeEngine.from_id("ai_optical_module")


def _state(trend="bull", style="growth", risk="high", liq="neutral"):
    return RegimeState(trend=trend, style=style, risk_appetite=risk,
                       liquidity=liq, as_of="2026-06-06")


# ── 结构访问 ──────────────────────────────────────────────────
def test_bottleneck_is_optical_module():
    eng = _engine()
    bn = eng.bottleneck()
    assert bn is not None and "光模块" in bn["name"]


def test_accessors():
    eng = _engine()
    assert eng.board_codes() == ["BK0457"]
    assert "光模块" in eng.industry_keywords()
    assert eng.fundamental_emphasis()["growth"] == 0.30
    assert any("传输速率" in v["name"] for v in eng.key_variables())


# ── 激活判断 ──────────────────────────────────────────────────
def test_active_in_growth_regime():
    eng = _engine()
    act = eng.evaluate(_state(style="growth", risk="high"), industry_prosperity=0.72)
    assert act.active is True
    assert any("政策支持" in r for r in act.reasons)
    assert any("行业景气 0.72" in r for r in act.reasons)


def test_inactive_in_value_regime():
    eng = _engine()
    # 价值风格不在 [growth, balanced] → 不激活
    act = eng.evaluate(_state(style="value"), industry_prosperity=0.72)
    assert act.active is False
    assert any("✗ 市场状态 style=value" in r for r in act.reasons)


def test_inactive_low_prosperity():
    eng = _engine()
    act = eng.evaluate(_state(), industry_prosperity=0.40)  # < 0.6 阈值
    assert act.active is False
    assert any("✗ 行业景气" in r for r in act.reasons)


def test_prosperity_pending_does_not_block():
    eng = _engine()
    # 景气未提供时不否决，但标注待补
    act = eng.evaluate(_state(), industry_prosperity=None)
    assert act.active is True
    assert any("行业景气未提供" in r for r in act.reasons)


# ── 候选池解析 ────────────────────────────────────────────────
def test_pool_seeds_only():
    pool = _engine().resolve_pool(members=None)
    assert pool.seeds == ["300308.SZ", "300502.SZ", "300394.SZ"]
    assert pool.enriched == pool.seeds


def test_pool_enriched_by_board_and_keyword():
    members = pd.DataFrame({
        "industry_code": ["BK0457", "BK0457", "BK9999"],
        "symbol": ["301205", "300308", "600519"],   # 301205 新成员；300308 已在种子；600519 无关
        "name": ["联特科技", "中际旭创", "贵州茅台"],
    })
    pool = _engine().resolve_pool(members=members)
    assert "301205.SZ" in pool.enriched     # 同板块新成员被纳入
    assert "600519.SH" not in pool.enriched  # 非相关板块/关键词不纳入
    assert pool.enriched.count("300308.SZ") == 1  # 已在种子，不重复
    assert "增强" in pool.note


def test_pool_enriched_by_keyword_match():
    members = pd.DataFrame({
        "industry_code": ["BKxxxx"],
        "symbol": ["688525"],
        "name": ["某某光模块科技"],   # 名称含关键词「光模块」
    })
    pool = _engine().resolve_pool(members=members)
    assert "688525.SH" in pool.enriched
