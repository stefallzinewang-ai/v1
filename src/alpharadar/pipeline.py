"""端到端流水线编排：把八层串起来跑一条主线。

读本地已采集数据 → 判市场状态 → 主线激活 → 候选池 → 基本面+动量打分 →
融合选股 → 生成报告。供 CLI `run` 调用。

设计为「数据缺失时优雅降级」：缺指数则无市场状态，缺财务则无候选，
但流程不崩，报告会如实标注。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings
from .data.store import DataStore
from .theme import ThemeEngine
from .regime.detector import RegimeDetector, DEFAULT_INDICES
from .fundamental.scorer import FundamentalScorer
from .factors.library import compute_momentum, standardize
from .selection.selector import Selector
from .report.builder import ReportBuilder


@dataclass
class PipelineResult:
    regime: Any = None
    activation: Any = None
    pool: Any = None
    candidates: list = None
    report: str = ""


def _seed_names(eng: ThemeEngine) -> dict[str, str]:
    from .data import schema as S

    out = {}
    for item in eng.theme.raw.get("candidate_pool", {}).get("seed_symbols", []):
        if "symbol" in item:
            out[S.normalize_symbol(item["symbol"])] = item.get("name", item["symbol"])
    return out


def run_pipeline(theme_id: str, as_of: str | None = None,
                 settings: Settings | None = None) -> PipelineResult:
    settings = settings or Settings.load()
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    eng = ThemeEngine.from_id(theme_id)
    pit = as_of or "2025-12-31"

    # 1) 市场状态
    indices_map = settings.get("regime", "indices", default=None) or DEFAULT_INDICES
    idx_bars = store.read_bars(symbols=list(indices_map.values()))
    regime = None
    if not idx_bars.empty:
        regime = RegimeDetector(
            trend_ma_window=settings.get("regime", "trend_ma_window", default=200),
            smoothing_days=settings.get("regime", "smoothing_days", default=5),
            indices=indices_map,
        ).detect(idx_bars, as_of=as_of)

    # 2) 主线激活（景气因子未就绪 → None，不否决）
    activation = eng.evaluate(regime, industry_prosperity=None) if regime else None

    # 3) 候选池
    industry = store.read_table("industry")
    pool = eng.resolve_pool(industry if not industry.empty else None)

    # 4) 基本面 + 动量打分
    fin = store.read_table("financials")
    if not fin.empty:
        fin = fin[fin["symbol"].isin(pool.enriched)]
    fund = FundamentalScorer(emphasis=eng.fundamental_emphasis()).score(fin, as_of=pit) \
        if not fin.empty else fund_empty()

    dims: dict[str, Any] = {}
    periods: dict[str, str] = {}
    if not fund.empty:
        dims["growth"] = fund["growth"]
        dims["quality"] = fund["quality"]
        periods = {sym: str(p) for sym, p in fund["report_period"].items()}

    cand_bars = store.read_bars(symbols=pool.enriched)
    if not cand_bars.empty:
        mom_raw = compute_momentum(cand_bars, as_of=as_of)
        if not mom_raw.empty:
            mom = standardize(mom_raw)
            dims["momentum"] = mom.reindex(fund.index).fillna(0.0) if not fund.empty else mom

    # 5) 融合选股
    candidates: list = []
    if dims:
        candidates = Selector(top_n=settings.get("selection", "top_n", default=2)).select(
            dims, weights=eng.fundamental_emphasis(),
            names=_seed_names(eng), periods=periods)

    # 6) 报告
    report = ReportBuilder(fmt=settings.get("report", "format", default="markdown")).build(
        theme_name=eng.theme.name, as_of=pit, regime=regime, activation=activation,
        bottleneck=eng.bottleneck(), key_variables=eng.key_variables(),
        candidates=candidates)

    return PipelineResult(regime=regime, activation=activation, pool=pool,
                          candidates=candidates, report=report)


def fund_empty():
    import pandas as pd

    return pd.DataFrame(columns=["report_period", "ann_date", "growth", "quality", "total"])
