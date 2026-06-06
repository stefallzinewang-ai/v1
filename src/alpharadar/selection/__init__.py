"""第 6 层 · 选股

把规律(3)/主线(4)/基本面(5)的分数按当前市场状态加权融合，输出 Top 1~2。
详见 docs/methodology.md §6。
"""
from .selector import Candidate, Selector

__all__ = ["Candidate", "Selector"]
