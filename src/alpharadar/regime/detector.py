"""市场状态识别器。

用多维标签刻画市场状态（而非单一牛熊），见 docs/methodology.md §1。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd

Trend = Literal["bull", "bear", "range"]
Style = Literal["growth", "value", "balanced"]
RiskAppetite = Literal["high", "neutral", "low"]
Liquidity = Literal["easing", "neutral", "tightening"]


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


class RegimeDetector:
    """从指数行情 + 宏观指标推断市场状态。"""

    def __init__(self, trend_ma_window: int = 200, smoothing_days: int = 5) -> None:
        self.trend_ma_window = trend_ma_window
        self.smoothing_days = smoothing_days

    def detect(
        self,
        index_bars: "pd.DataFrame",
        macro: "pd.DataFrame",
        as_of: str,
    ) -> RegimeState:
        """推断 as_of 当日的市场状态。

        阶段 2 规则版 baseline：
            trend         ← 宽基相对 200 日均线位置 + 斜率 + 新高新低；
            style         ← 成长/价值指数相对强弱；
            risk_appetite ← 小盘/大盘比值 + 波动率 + 两融变化；
            liquidity     ← M2/社融同比 + 利率 + 央行操作。
        切换需经 smoothing_days 确认，避免抖动。
        """
        # TODO(阶段2): 见 docstring；先实现可解释的规则版。
        raise NotImplementedError("RegimeDetector.detect 待阶段 2 实现")
