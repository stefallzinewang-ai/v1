"""本地存储：时间序列 → parquet 列存，水位线 → SQLite。

布局见 docs/data-model.md §5。用 pandas+pyarrow 读写 parquet，无需数据库部署。
DuckDB 为后续可选的查询加速，不是必需。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from . import schema as S


class DataStore:
    """统一读写本地数据。"""

    def __init__(self, root: str | Path = "./data_store") -> None:
        self.root = Path(root)
        self.bars_dir = self.root / "bars"
        self.financials_dir = self.root / "financials"
        self.macro_dir = self.root / "macro"
        self.industry_dir = self.root / "industry"
        self.meta_db = self.root / "meta.sqlite"

    def ensure_dirs(self) -> None:
        for d in (self.bars_dir, self.financials_dir, self.macro_dir, self.industry_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._init_meta()

    # ── 元数据 / 水位线（SQLite）──────────────────────────────
    def _init_meta(self) -> None:
        with sqlite3.connect(self.meta_db) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS watermark ("
                "  table_name TEXT, key TEXT, last_date TEXT,"
                "  PRIMARY KEY (table_name, key))"
            )

    def set_watermark(self, table: str, key: str, last_date: str) -> None:
        """记录某表某 key（如 symbol）已采集到的最新日期。"""
        self.ensure_dirs()
        with sqlite3.connect(self.meta_db) as con:
            con.execute(
                "INSERT INTO watermark(table_name,key,last_date) VALUES(?,?,?) "
                "ON CONFLICT(table_name,key) DO UPDATE SET last_date=excluded.last_date",
                (table, key, last_date),
            )

    def watermark(self, table: str, key: str) -> str | None:
        if not self.meta_db.exists():
            return None
        with sqlite3.connect(self.meta_db) as con:
            row = con.execute(
                "SELECT last_date FROM watermark WHERE table_name=? AND key=?",
                (table, key),
            ).fetchone()
        return row[0] if row else None

    # ── 行情 bars（按年分区 parquet）────────────────────────────
    def write_bars(self, df: pd.DataFrame) -> None:
        """写入行情，按年分区追加；同 (symbol,date) 去重保留最新。"""
        if df.empty:
            return
        self.ensure_dirs()
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        for year, chunk in df.groupby(df["date"].dt.year):
            path = self.bars_dir / f"year={year}" / "part.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                old = pd.read_parquet(path)
                chunk = pd.concat([old, chunk], ignore_index=True)
            chunk = (chunk.drop_duplicates(subset=["symbol", "date"], keep="last")
                          .sort_values(["symbol", "date"]))
            chunk.to_parquet(path, index=False)
        # 更新各 symbol 水位线
        for sym, g in df.groupby("symbol"):
            self.set_watermark("bars", str(sym), g["date"].max().strftime("%Y-%m-%d"))

    def read_bars(self, symbols=None, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        """读取行情，可按 symbols/日期范围过滤。"""
        files = sorted(self.bars_dir.glob("year=*/part.parquet"))
        if not files:
            return pd.DataFrame(columns=S.BARS_COLUMNS)
        df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
        df["date"] = pd.to_datetime(df["date"])
        if symbols is not None:
            wanted = {S.normalize_symbol(s) for s in symbols}
            df = df[df["symbol"].isin(wanted)]
        if start is not None:
            df = df[df["date"] >= pd.to_datetime(start)]
        if end is not None:
            df = df[df["date"] <= pd.to_datetime(end)]
        return df.sort_values(["symbol", "date"]).reset_index(drop=True)

    # ── 通用表（financials / industry 等单文件 parquet）─────────
    def write_table(self, name: str, df: pd.DataFrame, subset: list[str] | None = None) -> None:
        if df.empty:
            return
        self.ensure_dirs()
        path = self.root / name / "data.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        if subset:
            df = df.drop_duplicates(subset=subset, keep="last")
        df.to_parquet(path, index=False)

    def read_table(self, name: str) -> pd.DataFrame:
        path = self.root / name / "data.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()
