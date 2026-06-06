"""市场状态识别器。

用多维标签刻画市场状态（而非单一牛熊），见 docs/methodology.md §1。
判断逻辑写成纯函数（输入价格序列 → 输出标签），可用合成数据完全离线验证。

四个维度：
    trend          趋势      ← 宽基相对长期均线位置 + 均线斜率
    style          风格      ← 成长指数 vs 价值指数 的相对强弱
    risk_appetite  风险偏好  ← 小盘 vs 大盘 的相对强弱
    liquidity      流动性    ← 宏观（M2/利率），未接入时默认 neutral
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Mapping

if TYPE_CHECKING:
    import pandas as pd

Trend = Literal["bull", "bear", "range"]
Style = Literal["growth", "value", "balanced"]
RiskAppetite = Literal["high", "neutral", "low"]
Liquidity = Literal["easing", "neutral", "tightening"]

# 角色 → 指数代码 默认映射（可被 settings.regime.indices 覆盖）
DEFAULT_INDICES: dict[str, str] = {
    "broad": "000300.SH",   # 沪深300：趋势基准
    "growth": "399006.SZ",  # 创业板指：成长代表
    "value": "000016.SH",   # 上证50：价值代表
    "small": "000852.SH",   # 中证1000：小盘代表
    "large": "000016.SH",   # 上证50：大盘代表
}


@dataclass(frozen=True)
class RegimeState:
    """某一时点的市场状态四维标签。"""

    trend: Trend
    style: Style
    risk_appetite: RiskAppetite
    liquidity: Liquidity
    as_of: str  # YYYY-MM-DD

    def matches(self, criteria: dict) -> bool:
        """判断当前状态是否满足主线触发条件（themes 的 triggers.market_state）。

        criteria 形如 {"style": ["growth", "balanced"], "risk_appetite": ["high"]}，
        每个维度给一个允许取值列表；未列出的维度不约束。
        """
        for dim, allowed in criteria.items():
            value = getattr(self, dim, None)
            if value is not None and value not in allowed:
                return False
        return True

    def key(self) -> str:
        """状态键，用于规律挖掘按状态分组（如 'bull|growth|high'）。"""
        return f"{self.trend}|{self.style}|{self.risk_appetite}"


# ══════════════════════════════════════════════════════════════
# 纯分类函数（可用合成数据离线单测）
# ══════════════════════════════════════════════════════════════
def classify_trend(close: "pd.Series", ma_window: int = 200, slope_window: int = 20) -> Trend:
    """趋势：价格相对长期均线的位置 + 均线斜率。

    bull：价格在均线上方且均线上行；bear：价格在均线下方且均线下行；其余 range。
    数据不足 ma_window 时自适应缩短窗口。
    """
    close = close.dropna()
    n = len(close)
    if n < 2:
        return "range"
    w = ma_window if n >= ma_window else max(2, n // 2)
    ma = close.rolling(w).mean().dropna()
    if ma.empty:
        return "range"
    price = float(close.iloc[-1])
    ma_now = float(ma.iloc[-1])
    sw = min(slope_window, len(ma) - 1)
    ma_prev = float(ma.iloc[-1 - sw]) if sw > 0 else ma_now
    rising, falling = ma_now > ma_prev, ma_now < ma_prev
    if price > ma_now and rising:
        return "bull"
    if price < ma_now and falling:
        return "bear"
    return "range"


def trend_smoothed(close: "pd.Series", ma_window: int = 200,
                   smoothing_days: int = 5) -> Trend:
    """对最近 smoothing_days 天分别判趋势再多数表决，抑制抖动。"""
    close = close.dropna()
    votes = []
    for i in range(max(1, smoothing_days)):
        sub = close.iloc[: len(close) - i]
        if len(sub) >= 2:
            votes.append(classify_trend(sub, ma_window))
    if not votes:
        return "range"
    return Counter(votes).most_common(1)[0][0]


def _relative_momentum(a: "pd.Series", b: "pd.Series", lookback: int) -> float | None:
    """a 相对 b 在 lookback 个交易日内的超额涨幅。数据不足返回 None。"""
    import pandas as pd

    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(df) <= lookback:
        lookback = len(df) - 1
    if lookback < 1:
        return None
    ratio = df["a"] / df["b"]
    return float(ratio.iloc[-1] / ratio.iloc[-1 - lookback] - 1.0)


def classify_style(growth: "pd.Series", value: "pd.Series",
                   lookback: int = 63, threshold: float = 0.03) -> Style:
    """风格：成长 vs 价值的相对强弱（近一季度）。"""
    rel = _relative_momentum(growth, value, lookback)
    if rel is None:
        return "balanced"
    if rel > threshold:
        return "growth"
    if rel < -threshold:
        return "value"
    return "balanced"


def classify_risk_appetite(small: "pd.Series", large: "pd.Series",
                           lookback: int = 63, threshold: float = 0.03) -> RiskAppetite:
    """风险偏好：小盘 vs 大盘的相对强弱。小盘占优=风险偏好高。"""
    rel = _relative_momentum(small, large, lookback)
    if rel is None:
        return "neutral"
    if rel > threshold:
        return "high"
    if rel < -threshold:
        return "low"
    return "neutral"


def classify_liquidity(macro: "pd.DataFrame | None", as_of) -> Liquidity:
    """流动性：依赖宏观（M2/社融/利率）。未接入宏观数据时返回 neutral。"""
    if macro is None or len(macro) == 0:
        return "neutral"
    # TODO(宏观接入后): 比较 m2_yoy / 社融 / 利率 的边际变化，判 easing/tightening。
    return "neutral"


# ══════════════════════════════════════════════════════════════
# 识别器（薄编排层）
# ══════════════════════════════════════════════════════════════
class RegimeDetector:
    """从指数行情 + 宏观指标推断市场状态。"""

    def __init__(self, trend_ma_window: int = 200, smoothing_days: int = 5,
                 indices: Mapping[str, str] | None = None) -> None:
        self.trend_ma_window = trend_ma_window
        self.smoothing_days = smoothing_days
        self.indices = dict(DEFAULT_INDICES, **(indices or {}))

    def _series(self, index_bars: "pd.DataFrame", role: str, as_of) -> "pd.Series | None":
        """从长表里取某角色指数在 as_of 之前的收盘序列（按日期索引）。"""
        from ..data import schema as S

        symbol = self.indices.get(role)
        if symbol is None:
            return None
        want = S.normalize_symbol(symbol)
        sub = index_bars[index_bars["symbol"].map(S.normalize_symbol) == want]
        sub = sub[sub["date"] <= as_of].sort_values("date")
        if sub.empty:
            return None
        return sub.set_index("date")["close"]

    def detect(self, index_bars: "pd.DataFrame", macro: "pd.DataFrame | None" = None,
               as_of: str | None = None) -> RegimeState:
        """推断 as_of 当日的市场状态。

        index_bars 为长表（含多只指数，列同 bars schema）。各维度按角色取序列，
        缺失角色优雅降级（趋势→range，风格→balanced，风险→neutral，流动性→neutral）。
        """
        import pandas as pd

        bars = index_bars.copy()
        bars["date"] = pd.to_datetime(bars["date"])
        as_of_ts = pd.to_datetime(as_of) if as_of else bars["date"].max()

        broad = self._series(bars, "broad", as_of_ts)
        trend: Trend = (
            trend_smoothed(broad, self.trend_ma_window, self.smoothing_days)
            if broad is not None else "range"
        )

        g, v = self._series(bars, "growth", as_of_ts), self._series(bars, "value", as_of_ts)
        style = classify_style(g, v) if g is not None and v is not None else "balanced"

        s, l = self._series(bars, "small", as_of_ts), self._series(bars, "large", as_of_ts)
        risk = classify_risk_appetite(s, l) if s is not None and l is not None else "neutral"

        liquidity = classify_liquidity(macro, as_of_ts)

        return RegimeState(
            trend=trend, style=style, risk_appetite=risk, liquidity=liquidity,
            as_of=as_of_ts.strftime("%Y-%m-%d"),
        )
