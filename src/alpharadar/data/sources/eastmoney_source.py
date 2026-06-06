"""东方财富数据源（内置主数据源，零额外重依赖）。

设计要点：**解析逻辑（纯函数）与 HTTP 抓取分离**。
所有 `parse_*` 函数只接收原始 JSON dict、返回标准 schema 的 DataFrame，
因此可用离线样本完全单测；抓取方法只是「取 JSON → 调 parser」的薄壳。

接口对应的东方财富 API：
    daily_bars / index_bars  → push2his 行情 K 线
    industry_members         → push2 clist 板块成分
    financials               → datacenter 业绩报表 RPT_LICO_FN_CPD（含公告日）
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd

from .base import DataSource
from ..http import HttpClient
from .. import schema as S

# ── API 端点 ──────────────────────────────────────────────────
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
FINANCIALS_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# K 线 fields2 字段顺序（注意是 开/收/高/低，不是 OHLC）
_KLINE_FIELDS = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
# 复权：0 不复权 / 1 前复权 / 2 后复权
_FQ_HFQ = 2
_KLT_DAILY = 101


# ══════════════════════════════════════════════════════════════
# 纯解析函数（可离线单测）
# ══════════════════════════════════════════════════════════════
def parse_kline(payload: dict, symbol: str) -> pd.DataFrame:
    """东方财富 K 线 JSON → 标准 bars DataFrame。"""
    data = (payload or {}).get("data") or {}
    klines = data.get("klines") or []
    rows = []
    for line in klines:
        p = line.split(",")
        # 顺序：日期,开,收,高,低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
        rows.append({
            "symbol": S.normalize_symbol(symbol),
            "date": p[0],
            "open": p[1], "close": p[2], "high": p[3], "low": p[4],
            "volume": p[5], "amount": p[6], "turnover": p[10] if len(p) > 10 else None,
        })
    df = pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "high",
                                     "low", "volume", "amount", "turnover"])
    if df.empty:
        return df.reindex(columns=S.BARS_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    for col in ("open", "high", "low", "close", "volume", "amount", "turnover"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reindex(columns=S.BARS_COLUMNS).sort_values("date").reset_index(drop=True)


def parse_clist_members(payload: dict, industry_code: str) -> pd.DataFrame:
    """板块成分 clist JSON → 标准成分股 DataFrame。"""
    diff = ((payload or {}).get("data") or {}).get("diff") or []
    # diff 可能是 dict（按序号）或 list，统一成 list
    items = list(diff.values()) if isinstance(diff, dict) else diff
    rows = [
        {
            "industry_code": industry_code,
            "symbol": S.normalize_symbol(str(it["f12"])),
            "name": it.get("f14", ""),
        }
        for it in items if it.get("f12")
    ]
    return pd.DataFrame(rows, columns=S.INDUSTRY_MEMBER_COLUMNS)


def parse_financials(payload: dict) -> pd.DataFrame:
    """业绩报表 RPT_LICO_FN_CPD JSON → 标准 financials DataFrame（含公告日）。"""
    data = ((payload or {}).get("result") or {}).get("data") or []
    rows = []
    for it in data:
        rows.append({
            "symbol": S.normalize_symbol(str(it.get("SECURITY_CODE", ""))),
            "report_period": it.get("REPORT_DATE"),
            "ann_date": it.get("NOTICE_DATE"),          # 公告日：point-in-time 关键
            "revenue": it.get("TOTAL_OPERATE_INCOME"),
            "revenue_yoy": it.get("YSTZ"),               # 营收同比
            "net_profit": it.get("PARENT_NETPROFIT"),
            "net_profit_yoy": it.get("SJLTZ"),           # 净利同比
            "gross_margin": it.get("XSMLL"),             # 销售毛利率
            "roe": it.get("WEIGHTAVG_ROE"),
            "ocf": it.get("MGJYXJJE"),                   # 每股经营现金流（占位，可换总额）
        })
    df = pd.DataFrame(rows, columns=S.FINANCIALS_COLUMNS)
    if df.empty:
        return df
    for col in ("report_period", "ann_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    for col in ("revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
                "gross_margin", "roe", "ocf"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["symbol", "report_period"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
# 数据源实现（薄抓取层）
# ══════════════════════════════════════════════════════════════
class EastmoneySource(DataSource):
    """直连东方财富的 A 股数据源。"""

    def __init__(self, rate_limit_per_min: int = 60, max_retries: int = 4) -> None:
        self.http = HttpClient(rate_limit_per_min=rate_limit_per_min, max_retries=max_retries)

    def _kline(self, secid: str, symbol: str, start: str, end: str) -> pd.DataFrame:
        params = {
            "secid": secid, "klt": _KLT_DAILY, "fqt": _FQ_HFQ,
            "fields1": "f1,f2,f3,f4,f5,f6", "fields2": _KLINE_FIELDS,
            "beg": start.replace("-", ""), "end": end.replace("-", ""),
        }
        return parse_kline(self.http.get_json(KLINE_URL, params), symbol)

    def daily_bars(self, symbols: Sequence[str], start: str, end: str) -> pd.DataFrame:
        frames = [self._kline(S.to_secid(s), s, start, end) for s in symbols]
        out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=S.BARS_COLUMNS)
        return out

    def index_bars(self, index_code: str, start: str, end: str) -> pd.DataFrame:
        # 指数用专门的 secid 映射（不能按个股首位数字判断交易所）
        return self._kline(S.to_index_secid(index_code), index_code, start, end)

    def industry_members(self, industry: str) -> pd.DataFrame:
        # industry 传板块代码，如 'BK0457'（光通信）
        params = {
            "pn": 1, "pz": 500, "po": 1, "np": 1, "fltt": 2, "invt": 2,
            "fs": f"b:{industry}", "fields": "f12,f14",
        }
        return parse_clist_members(self.http.get_json(CLIST_URL, params), industry)

    def stock_universe(self, max_count: int = 6000) -> pd.DataFrame:
        """全 A 股列表（沪深京），仅含代码与名称。用于规律挖掘/回测的股票池。

        fs 用空格分隔（requests 会把空格编码为 '+'，正是东方财富所需格式）。
        ⚠️ 该接口需在可访问东方财富的机器上验证；解析复用已测的 clist 解析器。
        """
        fs = "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048"
        params = {
            "pn": 1, "pz": max_count, "po": 1, "np": 1, "fltt": 2, "invt": 2,
            "fs": fs, "fields": "f12,f14",
        }
        df = parse_clist_members(self.http.get_json(CLIST_URL, params), "")
        return df[["symbol", "name"]]

    def financials(self, symbols: Sequence[str], start: str, end: str) -> pd.DataFrame:
        cols = ("SECURITY_CODE,REPORT_DATE,NOTICE_DATE,TOTAL_OPERATE_INCOME,"
                "YSTZ,PARENT_NETPROFIT,SJLTZ,XSMLL,WEIGHTAVG_ROE,MGJYXJJE")
        frames = []
        for sym in symbols:
            params = {
                "reportName": "RPT_LICO_FN_CPD", "columns": cols,
                "filter": f'(SECURITY_CODE="{S.code6(sym)}")',
                "pageSize": 200, "sortColumns": "REPORT_DATE", "sortTypes": -1,
            }
            frames.append(parse_financials(self.http.get_json(FINANCIALS_URL, params)))
        out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=S.FINANCIALS_COLUMNS)
        if not out.empty:
            mask = (out["report_period"] >= pd.to_datetime(start).date()) & \
                   (out["report_period"] <= pd.to_datetime(end).date())
            out = out[mask].reset_index(drop=True)
        return out

    def macro(self, indicators: Sequence[str], start: str, end: str) -> pd.DataFrame:
        # TODO(阶段1+): 东方财富 datacenter 各宏观指标接口，逐项接入（cpi/ppi/pmi/m2…）。
        raise NotImplementedError("macro 待后续接入，见 docs/roadmap.md")
