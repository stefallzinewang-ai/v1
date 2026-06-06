"""研究报告生成器。

把整条逻辑链（市场状态 → 主线激活 → 瓶颈环节 → 候选公司 + 逐条理由）
渲染成人类可读、可追溯的 Markdown 报告。每个结论都能回溯到得分与数据。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..regime.detector import RegimeState
    from ..theme.chain import ThemeActivation
    from ..selection.selector import Candidate

DISCLAIMER = (
    "本报告由「主线雷达」基于历史数据自动生成，仅供研究与教育之用，"
    "不构成任何投资建议。股市有风险，历史规律不保证未来重演，决策与盈亏自负。"
)


class ReportBuilder:
    """把逻辑链渲染成 Markdown 报告。"""

    def __init__(self, fmt: str = "markdown") -> None:
        self.fmt = fmt

    def build(self, *, theme_name: str, as_of: str,
              regime: "RegimeState | None",
              activation: "ThemeActivation | None",
              bottleneck: dict | None,
              key_variables: list[dict] | None,
              candidates: list["Candidate"]) -> str:
        """生成完整研究报告（Markdown）。"""
        L: list[str] = []
        L.append(f"# 主线雷达 · 研究报告：{theme_name}")
        L.append(f"\n*生成时点（point-in-time）：{as_of}*\n")

        # 1. 市场状态
        L.append("## 一、市场状态")
        if regime is None:
            L.append("- 暂无指数数据，无法判断市场状态（请先 `sync`）。")
        else:
            L.append(f"- 趋势：**{regime.trend}**　风格：**{regime.style}**　"
                     f"风险偏好：**{regime.risk_appetite}**　流动性：**{regime.liquidity}**")
            L.append(f"- 状态键：`{regime.key()}`")

        # 2. 主线激活
        L.append("\n## 二、主线激活判断")
        if activation is None:
            L.append("- 未做激活判断（缺市场状态）。")
        else:
            L.append(f"- 结论：{'✅ **激活**' if activation.active else '⛔ **未激活**'}")
            for r in activation.reasons:
                L.append(f"  - {r}")

        # 3. 瓶颈环节
        L.append("\n## 三、产业链瓶颈环节")
        if bottleneck:
            L.append(f"- **{bottleneck.get('name')}** —— {bottleneck.get('note', '')}")
        if key_variables:
            L.append("- 关键变量（驱动股价的核心矛盾）：")
            for v in key_variables:
                L.append(f"  - {v.get('name')}（{v.get('metric')}）")

        # 4. 候选公司
        L.append("\n## 四、候选公司（Top {}）".format(len(candidates)))
        if not candidates:
            L.append("- 候选池内无可用数据（可能财务公告日晚于本时点，或尚未采集）。")
        else:
            for i, c in enumerate(candidates, 1):
                period = f"（最新报告期 {c.report_period}）" if c.report_period else ""
                L.append(f"\n### {i}. {c.name}（{c.symbol}）  总分 {c.total_score:+.2f}{period}")
                for r in c.reasons:
                    L.append(f"  - {r}")

        # 5. 免责
        L.append("\n---")
        L.append(f"> ⚠️ {DISCLAIMER}")
        return "\n".join(L)
