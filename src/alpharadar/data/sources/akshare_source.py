"""AKShare 数据源适配器（主数据源）。

AKShare 免费、覆盖 A 股行情/财务/宏观/行业，是本系统默认源。
本文件目前为接口骨架：每个方法标注了对应的 AKShare 接口，待阶段 1 填充。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from .base import DataSource

if TYPE_CHECKING:
    import pandas as pd


class AkshareSource(DataSource):
    """基于 AKShare 的数据源实现。

    注意：akshare 仅在实际调用时延迟导入，使骨架在未安装时也能 import。
    """

    def __init__(self, rate_limit_per_min: int = 60, max_retries: int = 4) -> None:
        self.rate_limit_per_min = rate_limit_per_min
        self.max_retries = max_retries

    @staticmethod
    def _akshare():
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "未安装 akshare，请先 `pip install akshare`（见 requirements.txt）。"
            ) from exc
        return ak

    def daily_bars(self, symbols: Sequence[str], start: str, end: str) -> "pd.DataFrame":
        # TODO(阶段1): ak.stock_zh_a_hist(symbol, period='daily', adjust='hfq')
        #   逐 symbol 拉取 → 标准化列名 → 加交易所后缀 → 限速重试 → 合并返回。
        raise NotImplementedError("daily_bars 待阶段 1 实现，见 docs/roadmap.md")

    def index_bars(self, index_code: str, start: str, end: str) -> "pd.DataFrame":
        # TODO(阶段1): ak.stock_zh_index_daily / index_zh_a_hist
        raise NotImplementedError("index_bars 待阶段 1 实现")

    def financials(self, symbols: Sequence[str], start: str, end: str) -> "pd.DataFrame":
        # TODO(阶段1): ak.stock_financial_abstract / stock_financial_report_sina
        #   关键：保留 ann_date（公告日），用于 point-in-time 切片防未来函数。
        raise NotImplementedError("financials 待阶段 1 实现")

    def macro(self, indicators: Sequence[str], start: str, end: str) -> "pd.DataFrame":
        # TODO(阶段1): ak.macro_china_* （cpi/ppi/pmi/m2/社融/利率 等）
        raise NotImplementedError("macro 待阶段 1 实现")

    def industry_members(self, industry: str) -> "pd.DataFrame":
        # TODO(阶段1): ak.stock_board_industry_cons_em / stock_board_concept_cons_em
        raise NotImplementedError("industry_members 待阶段 1 实现")
