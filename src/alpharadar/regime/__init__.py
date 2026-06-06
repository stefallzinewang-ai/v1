"""第 2 层 · 市场状态识别

输入宏观 + 指数行情，输出当前「市场状态」多维标签。
是整个系统的「开关」：不同状态下启用不同规律。详见 docs/methodology.md §1。
"""
from .detector import RegimeState, RegimeDetector

__all__ = ["RegimeState", "RegimeDetector"]
