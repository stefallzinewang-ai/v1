"""产业链引擎：加载主线配置，定位瓶颈环节，圈定候选股池。

人工骨架（YAML）+ 数据增强（行业景气/成分股）。详见 docs/methodology.md §4。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import ThemeConfig

if TYPE_CHECKING:
    from ..regime.detector import RegimeState


class ThemeEngine:
    """围绕一条主线（ThemeConfig）提供查询与激活判断。"""

    def __init__(self, theme: ThemeConfig) -> None:
        self.theme = theme

    @classmethod
    def from_id(cls, theme_id: str) -> "ThemeEngine":
        return cls(ThemeConfig.load(theme_id))

    def is_active(self, regime: "RegimeState", industry_prosperity: float) -> bool:
        """判断当前是否满足主线触发条件（triggers）。

        条件来自 YAML 的 triggers：市场状态匹配 + 行业景气达标 + 政策支持。
        """
        triggers = self.theme.raw.get("triggers", {})
        state_ok = regime.matches(triggers.get("market_state", {}))
        prosperity_ok = industry_prosperity >= triggers.get("industry_prosperity_min", 0.0)
        policy_ok = True
        if triggers.get("require_policy_support"):
            policy_ok = any(
                s.get("direction") == "support"
                for s in self.theme.raw.get("policy_signals", [])
            )
        return state_ok and prosperity_ok and policy_ok

    def bottleneck(self) -> dict | None:
        """返回瓶颈环节（如光模块）。"""
        return self.theme.bottleneck_stage

    def candidate_symbols(self, enrich: bool = False) -> list[str]:
        """返回候选股池。

        enrich=False：仅返回 YAML 种子股；
        enrich=True ：阶段 4 用 industry_keywords 从行业成分自动补全/校验。
        """
        seeds = self.theme.seed_symbols
        if not enrich:
            return seeds
        # TODO(阶段4): 用 candidate_pool.industry_keywords 拉行业成分，合并去重。
        raise NotImplementedError("候选池数据增强待阶段 4 实现")
