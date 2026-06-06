"""第 3 层 · 规律挖掘（系统大脑）

用 15 年历史，按市场状态分组，挖掘「会上涨的股票」的因子共性，
产出带权重、带适用状态的 Pattern。详见 docs/methodology.md §3。
"""
from .pattern_miner import Pattern, PatternMiner

__all__ = ["Pattern", "PatternMiner"]
