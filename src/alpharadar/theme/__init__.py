"""第 4 层 · 主线映射

把抽象主题落到具体股票池的产业链知识库：主题 → 环节 → 瓶颈 → 候选股。
配置驱动（themes/*.yaml）+ 数据增强。详见 docs/methodology.md §4。
"""
from .chain import ThemeEngine

__all__ = ["ThemeEngine"]
