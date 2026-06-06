"""阶段 1 数据层测试：解析器（离线样本）、存储、采集编排。

不触网：解析器用 tests/fixtures 下的样本 JSON 验证；
采集编排用 FakeSource 注入数据，验证增量逻辑。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")  # 存储用 parquet

import pandas as pd  # noqa: E402

from alpharadar.data import schema as S  # noqa: E402
from alpharadar.data.sources.eastmoney_source import (  # noqa: E402
    parse_kline, parse_clist_members, parse_financials,
)
from alpharadar.data.store import DataStore  # noqa: E402
from alpharadar.data.ingest import Ingestor, validate_bars  # noqa: E402
from alpharadar.data.sources.base import DataSource  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# ── 代码工具 ──────────────────────────────────────────────────
def test_symbol_normalization():
    assert S.normalize_symbol("300308") == "300308.SZ"
    assert S.normalize_symbol("600000") == "600000.SH"
    assert S.normalize_symbol("sz300308") == "300308.SZ"
    assert S.normalize_symbol("1.600000") == "600000.SH"
    assert S.to_secid("300308") == "0.300308"
    assert S.to_secid("600000") == "1.600000"


def test_index_secid():
    # 指数按 399 前缀判市场，而非个股首位规则
    assert S.to_index_secid("399006") == "0.399006"   # 创业板指（深）
    assert S.to_index_secid("000300") == "1.000300"   # 沪深300（沪）
    assert S.to_index_secid("000016.SH") == "1.000016"  # 容忍带后缀


# ── 纯解析器（离线样本验证）────────────────────────────────────
def test_parse_kline():
    df = parse_kline(_load("eastmoney_kline.json"), "300308")
    assert list(df.columns) == S.BARS_COLUMNS
    assert len(df) == 3
    # 字段顺序映射正确：第一行 开=124.50 收=120.10 高=125.00 低=119.00
    row0 = df.iloc[0]
    assert row0["open"] == 124.50 and row0["close"] == 120.10
    assert row0["high"] == 125.00 and row0["low"] == 119.00
    assert row0["symbol"] == "300308.SZ"
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    # 已按日期升序
    assert df["date"].is_monotonic_increasing


def test_parse_clist_members():
    df = parse_clist_members(_load("eastmoney_clist.json"), "BK0457")
    assert list(df.columns) == S.INDUSTRY_MEMBER_COLUMNS
    assert set(df["symbol"]) == {"300308.SZ", "300502.SZ", "300394.SZ"}
    assert (df["industry_code"] == "BK0457").all()


def test_stock_universe_parses_without_network():
    from alpharadar.data.sources.eastmoney_source import EastmoneySource

    src = EastmoneySource()
    # 拦截 HTTP，喂入 clist 样本，验证 universe 返回代码/名称
    src.http.get_json = lambda url, params=None: _load("eastmoney_clist.json")
    uni = src.stock_universe()
    assert list(uni.columns) == ["symbol", "name"]
    assert "300308.SZ" in set(uni["symbol"])


def test_parse_financials_has_ann_date():
    df = parse_financials(_load("eastmoney_financials.json"))
    assert list(df.columns) == S.FINANCIALS_COLUMNS
    assert len(df) == 2
    # 公告日（point-in-time 关键）被正确解析
    r = df[df["report_period"].astype(str) == "2024-03-31"].iloc[0]
    assert str(r["ann_date"]) == "2024-04-25"
    assert r["revenue_yoy"] == 80.5
    assert r["symbol"] == "300308.SZ"


# ── 存储往返 ──────────────────────────────────────────────────
def test_store_bars_roundtrip(tmp_path):
    store = DataStore(root=tmp_path)
    df = parse_kline(_load("eastmoney_kline.json"), "300308")
    store.write_bars(df)
    back = store.read_bars(symbols=["300308"])
    assert len(back) == 3
    # 水位线记录最新日期
    assert store.watermark("bars", "300308.SZ") == "2024-01-04"
    # 重复写入应去重（不翻倍）
    store.write_bars(df)
    assert len(store.read_bars(symbols=["300308"])) == 3


def test_store_date_filter(tmp_path):
    store = DataStore(root=tmp_path)
    store.write_bars(parse_kline(_load("eastmoney_kline.json"), "300308"))
    sub = store.read_bars(start="2024-01-03", end="2024-01-04")
    assert len(sub) == 2


# ── 采集编排（FakeSource，不触网）──────────────────────────────
class FakeSource(DataSource):
    def __init__(self, bars):
        self._bars = bars
        self.calls = []

    def daily_bars(self, symbols, start, end):
        self.calls.append((tuple(symbols), start, end))
        df = self._bars
        df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
        return df.reset_index(drop=True)

    def index_bars(self, index_code, start, end):
        return self._bars

    def financials(self, symbols, start, end):
        return pd.DataFrame()

    def macro(self, indicators, start, end):
        return pd.DataFrame()

    def industry_members(self, industry):
        return pd.DataFrame()


def test_ingestor_incremental(tmp_path):
    bars = parse_kline(_load("eastmoney_kline.json"), "300308")
    source = FakeSource(bars)
    store = DataStore(root=tmp_path)
    ing = Ingestor(source, store)

    n1 = ing.sync_bars(["300308"], "2024-01-01", "2024-01-04")
    assert n1 == 3
    assert source.calls[0][1] == "2024-01-01"  # 首次从 start 抓
    # 第二次同步：水位线已到 01-04 覆盖整个区间，应直接跳过、不再触网
    n2 = ing.sync_bars(["300308"], "2024-01-01", "2024-01-04")
    assert n2 == 0
    assert len(source.calls) == 1  # 未发起新的抓取
    # 扩大 end 到 01-06：应只从水位线+1天（01-05）开始增量抓
    ing.sync_bars(["300308"], "2024-01-01", "2024-01-06")
    assert source.calls[-1][1] == "2024-01-05"


def test_validate_bars_drops_bad_rows():
    bad = pd.DataFrame({
        "symbol": ["x.SZ", "x.SZ"], "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "open": [10.0, -1.0], "high": [11.0, 5.0], "low": [9.0, 6.0],
        "close": [10.5, 5.0], "volume": [1, 1], "amount": [1, 1], "turnover": [0.1, 0.1],
    })
    # 第二行：开盘为负 且 high<low → 应被剔除
    assert len(validate_bars(bad)) == 1
