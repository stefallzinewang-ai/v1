"""标准数据 schema 与股票代码工具。

所有数据源的输出都要对齐到这里定义的列与代码格式（见 docs/data-model.md §4），
让上层与数据源无关。
"""
from __future__ import annotations

# ── 标准列定义 ────────────────────────────────────────────────
BARS_COLUMNS = [
    "symbol", "date", "open", "high", "low", "close",
    "volume", "amount", "turnover",
]

FINANCIALS_COLUMNS = [
    "symbol", "report_period", "ann_date",
    "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
    "gross_margin", "roe", "ocf",
]

INDUSTRY_MEMBER_COLUMNS = ["industry_code", "symbol", "name"]


# ── 股票代码工具 ──────────────────────────────────────────────
def exchange_of(code6: str) -> str:
    """根据 6 位代码判断交易所后缀。

    6/9 开头 → 上交所(SH)；0/2/3 开头 → 深交所(SZ)；4/8 开头 → 北交所(BJ)。
    """
    c = code6.strip()
    if c[:3] in ("688", "605", "603", "601", "600", "689") or c[0] in ("6", "9"):
        return "SH"
    if c[0] in ("4", "8"):
        return "BJ"
    return "SZ"


def normalize_symbol(raw: str) -> str:
    """把各种写法统一成 `300308.SZ` 形式。

    接受：'300308'、'300308.SZ'、'sz300308'、'SZ300308'、'0.300308'(secid)。
    """
    s = raw.strip().upper()
    if "." in s:
        left, right = s.split(".", 1)
        # secid 形式：'0.300308' / '1.600000'
        if left in ("0", "1") and right.isdigit():
            code = right
            return f"{code}.{'SH' if left == '1' else 'SZ'}"
        # 已是 '300308.SZ'
        if right in ("SH", "SZ", "BJ"):
            return f"{left}.{right}"
    # 'SZ300308' / 'sz300308'
    if s[:2] in ("SH", "SZ", "BJ"):
        code = s[2:]
        return f"{code}.{s[:2]}"
    # 纯 6 位
    return f"{s}.{exchange_of(s)}"


def to_secid(symbol: str) -> str:
    """把代码转成东方财富 secid：`0.300308`(深) / `1.600000`(沪)。"""
    norm = normalize_symbol(symbol)
    code, ex = norm.split(".")
    market = "1" if ex == "SH" else "0"  # 北交所在东方财富也用 0
    return f"{market}.{code}"


def code6(symbol: str) -> str:
    """取纯 6 位代码。"""
    return normalize_symbol(symbol).split(".")[0]
