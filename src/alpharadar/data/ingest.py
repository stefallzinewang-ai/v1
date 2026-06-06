"""数据采集编排：增量更新、校验、落地。

把 DataSource（取数）与 DataStore（落地）粘合，提供「把某段历史补齐到本地」的能力。
限速与重试在 HttpClient 内处理。详见 docs/data-model.md §6。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

import pandas as pd

from .sources.base import DataSource
from .store import DataStore
from . import schema as S


def _next_day(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def validate_bars(df: pd.DataFrame) -> pd.DataFrame:
    """行情基本一致性校验：去掉非正价格、high<low 等脏数据。"""
    if df.empty:
        return df
    ok = (df[["open", "high", "low", "close"]] > 0).all(axis=1) & (df["high"] >= df["low"])
    return df[ok].reset_index(drop=True)


class Ingestor:
    """采集编排器。"""

    def __init__(self, source: DataSource, store: DataStore) -> None:
        self.source = source
        self.store = store

    def sync_bars(self, symbols: Sequence[str], start: str, end: str) -> int:
        """增量同步行情到本地。返回新写入的行数。"""
        self.store.ensure_dirs()
        total = 0
        for raw in symbols:
            sym = S.normalize_symbol(raw)
            wm = self.store.watermark("bars", sym)
            fetch_start = _next_day(wm) if wm and wm >= start else start
            if fetch_start > end:
                continue  # 已是最新
            df = validate_bars(self.source.daily_bars([sym], fetch_start, end))
            if not df.empty:
                self.store.write_bars(df)
                total += len(df)
        return total

    def sync_indices(self, index_symbols: Sequence[str], start: str, end: str) -> int:
        """增量同步指数行情到本地（与个股共用 bars 存储，按 symbol 区分）。"""
        self.store.ensure_dirs()
        total = 0
        for raw in index_symbols:
            sym = S.normalize_symbol(raw)
            wm = self.store.watermark("bars", sym)
            fetch_start = _next_day(wm) if wm and wm >= start else start
            if fetch_start > end:
                continue
            df = validate_bars(self.source.index_bars(raw, fetch_start, end))
            if not df.empty:
                self.store.write_bars(df)
                total += len(df)
        return total

    def sync_financials(self, symbols: Sequence[str], start: str, end: str) -> int:
        self.store.ensure_dirs()
        df = self.source.financials(symbols, start, end)
        self.store.write_table("financials", df, subset=["symbol", "report_period"])
        return len(df)

    def sync_industry_members(self, industry_code: str) -> int:
        self.store.ensure_dirs()
        df = self.source.industry_members(industry_code)
        self.store.write_table("industry", df, subset=["industry_code", "symbol"])
        return len(df)
