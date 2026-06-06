"""第 7 层 · 回测

Point-in-time 事件回放：每个历史时点只用当时可得数据跑完整流水线，
统计候选股的后验收益/胜率/回撤，验证规律有效性。详见 docs/methodology.md §3.2。
"""
from .engine import BacktestEngine, BacktestResult

__all__ = ["BacktestEngine", "BacktestResult"]
