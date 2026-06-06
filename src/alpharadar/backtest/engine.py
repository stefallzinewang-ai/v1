"""回测引擎：严格无未来函数的事件回放。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BacktestResult:
    """回测统计结果。"""

    annual_excess_return: float | None = None  # 年化超额
    information_ratio: float | None = None      # 信息比率
    win_rate: float | None = None               # 胜率
    max_drawdown: float | None = None           # 最大回撤
    turnover: float | None = None               # 换手率
    by_regime: dict[str, dict] = field(default_factory=dict)  # 分状态表现

    def summary(self) -> str:
        return (
            f"年化超额={self.annual_excess_return}, IR={self.information_ratio}, "
            f"胜率={self.win_rate}, 最大回撤={self.max_drawdown}"
        )


class BacktestEngine:
    """在每个历史调仓点回放整条流水线并统计后验表现。"""

    def __init__(self, start: str, end: str, rebalance: str = "monthly") -> None:
        self.start = start
        self.end = end
        self.rebalance = rebalance

    def run(self) -> BacktestResult:
        """逐调仓点回放，统计收益/胜率/回撤。

        阶段 6 要点：
            - 每个时点只用 ann_date <= 当日的数据（point-in-time）；
            - 股票池含退市股；扣手续费与冲击成本；剔除停牌/涨跌停不可成交；
            - 同时输出分市场状态的表现，验证规律稳健性。
        """
        # TODO(阶段6): 见 docstring。
        raise NotImplementedError("BacktestEngine.run 待阶段 6 实现")
