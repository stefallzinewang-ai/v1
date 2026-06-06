"""产业链引擎：加载主线配置，判断激活，定位瓶颈环节，圈定候选股池。

人工骨架（YAML）+ 数据增强（行业成分）。判断逻辑可离线验证。
详见 docs/methodology.md §4。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..config import ThemeConfig
from ..data import schema as S

if TYPE_CHECKING:
    import pandas as pd
    from ..regime.detector import RegimeState


@dataclass
class ThemeActivation:
    """主线激活判断结果（带可解释理由，供报告层使用）。"""

    active: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class CandidatePool:
    """候选股池：YAML 种子 + 行业成分增强后的并集。"""

    seeds: list[str]
    enriched: list[str]
    note: str = ""


class ThemeEngine:
    """围绕一条主线（ThemeConfig）提供激活判断与候选池解析。"""

    def __init__(self, theme: ThemeConfig) -> None:
        self.theme = theme

    @classmethod
    def from_id(cls, theme_id: str) -> "ThemeEngine":
        return cls(ThemeConfig.load(theme_id))

    # ── 配置访问器 ────────────────────────────────────────────
    @property
    def triggers(self) -> dict:
        return self.theme.raw.get("triggers", {})

    def board_codes(self) -> list[str]:
        return self.theme.raw.get("candidate_pool", {}).get("board_codes", [])

    def industry_keywords(self) -> list[str]:
        return self.theme.raw.get("candidate_pool", {}).get("industry_keywords", [])

    def key_variables(self) -> list[dict]:
        return self.theme.raw.get("key_variables", [])

    def fundamental_emphasis(self) -> dict[str, float]:
        return self.theme.raw.get("fundamental_emphasis", {})

    def bottleneck(self) -> dict | None:
        """返回瓶颈环节（如光模块）。"""
        return self.theme.bottleneck_stage

    # ── 激活判断（带理由）────────────────────────────────────
    def evaluate(self, regime: "RegimeState",
                 industry_prosperity: float | None = None) -> ThemeActivation:
        """判断当前是否满足主线触发条件，返回带理由的结果。

        三道门：市场状态匹配、行业景气达标、政策支持。
        industry_prosperity 为 None 时（阶段 3 景气因子未就绪）该门暂不否决，
        但会在理由中标注「待补」。
        """
        reasons: list[str] = []
        ok = True

        # 1) 市场状态
        crit = self.triggers.get("market_state", {})
        for dim, allowed in crit.items():
            val = getattr(regime, dim, None)
            if val is not None and val not in allowed:
                ok = False
                reasons.append(f"✗ 市场状态 {dim}={val} 不在 {allowed}")
            else:
                reasons.append(f"✓ 市场状态 {dim}={val} ∈ {allowed}")

        # 2) 行业景气
        thr = self.triggers.get("industry_prosperity_min", 0.0)
        if industry_prosperity is None:
            reasons.append(f"… 行业景气未提供（阈值 {thr}，待阶段 3 景气因子）")
        elif industry_prosperity >= thr:
            reasons.append(f"✓ 行业景气 {industry_prosperity:.2f} ≥ {thr}")
        else:
            ok = False
            reasons.append(f"✗ 行业景气 {industry_prosperity:.2f} < {thr}")

        # 3) 政策支持
        if self.triggers.get("require_policy_support"):
            supports = [s for s in self.theme.raw.get("policy_signals", [])
                        if s.get("direction") == "support"]
            if supports:
                reasons.append(f"✓ 政策支持：{supports[0].get('tag', '')}")
            else:
                ok = False
                reasons.append("✗ 无政策支持信号")

        return ThemeActivation(active=ok, reasons=reasons)

    def is_active(self, regime: "RegimeState",
                  industry_prosperity: float | None = None) -> bool:
        return self.evaluate(regime, industry_prosperity).active

    # ── 候选股池解析（种子 + 成分增强，纯函数可测）──────────────
    def resolve_pool(self, members: "pd.DataFrame | None" = None) -> CandidatePool:
        """合并 YAML 种子股与行业成分（按板块代码或名称关键词匹配）。

        members：已采集的行业成分表（列：industry_code, symbol, name）。
        不提供时仅返回种子股。
        """
        seeds = [S.normalize_symbol(s) for s in self.theme.seed_symbols]
        enriched = list(seeds)
        note = "仅种子股"

        if members is not None and len(members) > 0:
            codes = set(self.board_codes())
            kws = self.industry_keywords()
            by_board = members["industry_code"].isin(codes) if codes else False
            by_kw = members["name"].apply(
                lambda nm: any(kw in str(nm) for kw in kws)) if kws else False
            mask = by_board | by_kw
            picked = members[mask] if mask is not False else members.iloc[0:0]
            for sym in picked["symbol"]:
                norm = S.normalize_symbol(str(sym))
                if norm not in enriched:
                    enriched.append(norm)
            note = f"种子 {len(seeds)} + 成分增强 {len(enriched) - len(seeds)}"

        return CandidatePool(seeds=seeds, enriched=enriched, note=note)
