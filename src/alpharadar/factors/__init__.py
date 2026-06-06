"""因子库（第 3、5 层共用）

把原始数据加工成可横截面比较的特征。五大类：景气/成长/质量/动量/估值。
详见 docs/methodology.md §2。
"""
from .library import FACTOR_CATEGORIES, Factor

__all__ = ["FACTOR_CATEGORIES", "Factor"]
