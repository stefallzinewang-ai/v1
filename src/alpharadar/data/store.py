"""本地存储抽象。

时间序列 → parquet 列存（DuckDB 直接 SQL 查询，免数据库部署）。
元数据/采集水位线 → SQLite。布局见 docs/data-model.md §5。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class DataStore:
    """统一读写本地数据。骨架阶段仅落定目录结构与接口。"""

    def __init__(self, root: str | Path = "./data_store") -> None:
        self.root = Path(root)
        self.bars_dir = self.root / "bars"
        self.financials_dir = self.root / "financials"
        self.macro_dir = self.root / "macro"
        self.industry_dir = self.root / "industry"
        self.meta_db = self.root / "meta.sqlite"

    def ensure_dirs(self) -> None:
        """创建数据目录骨架。"""
        for d in (self.bars_dir, self.financials_dir, self.macro_dir, self.industry_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── 读写（待阶段 1 实现）────────────────────────────────────
    def write_bars(self, df: "pd.DataFrame") -> None:
        # TODO(阶段1): 按 year 分区写 parquet；更新 SQLite 水位线。
        raise NotImplementedError("write_bars 待阶段 1 实现")

    def read_bars(self, symbols, start: str, end: str) -> "pd.DataFrame":
        # TODO(阶段1): DuckDB 扫描 parquet，按 symbol/date 过滤。
        raise NotImplementedError("read_bars 待阶段 1 实现")

    def watermark(self, table: str) -> str | None:
        """返回某表已采集到的最新日期（增量更新用）。待阶段 1 实现。"""
        raise NotImplementedError("watermark 待阶段 1 实现")
