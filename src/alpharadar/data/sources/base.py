"""统一数据源接口。

上层只依赖本接口，不依赖具体数据源（AKShare/Tushare/baostock 可插拔）。
返回的 DataFrame 一律遵循 docs/data-model.md 的标准列定义，与数据源无关。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # 仅类型检查时导入，避免运行时强依赖 pandas
    import pandas as pd


class DataSource(ABC):
    """所有数据源的抽象基类。

    实现者负责把各源的原始字段映射到标准 schema（见 data-model.md §4）。
    """

    @abstractmethod
    def daily_bars(
        self, symbols: Sequence[str], start: str, end: str
    ) -> "pd.DataFrame":
        """个股日线行情（后复权）。列：symbol,date,open,high,low,close,volume,amount,..."""

    @abstractmethod
    def index_bars(self, index_code: str, start: str, end: str) -> "pd.DataFrame":
        """指数日线行情。用于市场状态与基准。"""

    @abstractmethod
    def financials(
        self, symbols: Sequence[str], start: str, end: str
    ) -> "pd.DataFrame":
        """财务数据（point-in-time，含 ann_date 公告日）。"""

    @abstractmethod
    def macro(self, indicators: Sequence[str], start: str, end: str) -> "pd.DataFrame":
        """宏观经济指标。列：indicator,date,ann_date,value。"""

    @abstractmethod
    def industry_members(self, industry: str) -> "pd.DataFrame":
        """行业/概念板块成分股。列：industry_code,symbol,name。"""
