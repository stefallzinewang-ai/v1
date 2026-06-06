"""数据采集编排：增量更新、限速、重试、缓存。

把 DataSource（取数）与 DataStore（落地）粘合起来，对外提供「把某段历史
补齐到本地」的能力。详见 docs/data-model.md §6。
"""
from __future__ import annotations

from typing import Sequence

from .sources.base import DataSource
from .store import DataStore


class Ingestor:
    """采集编排器。"""

    def __init__(self, source: DataSource, store: DataStore) -> None:
        self.source = source
        self.store = store

    def sync_bars(self, symbols: Sequence[str], start: str, end: str) -> None:
        """增量同步行情到本地存储。

        阶段 1 逻辑：
            1. 读各 symbol 的水位线，计算待补区间；
            2. 限速 + 指数退避重试地拉取；
            3. 一致性校验后写入 parquet 并更新水位线。
        """
        # TODO(阶段1): 见 docstring 步骤。
        raise NotImplementedError("sync_bars 待阶段 1 实现，见 docs/roadmap.md 阶段 1")

    def sync_financials(self, symbols: Sequence[str], start: str, end: str) -> None:
        raise NotImplementedError("sync_financials 待阶段 1 实现")

    def sync_macro(self, indicators: Sequence[str], start: str, end: str) -> None:
        raise NotImplementedError("sync_macro 待阶段 1 实现")
