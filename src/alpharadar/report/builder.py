"""研究报告生成器。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..regime.detector import RegimeState
    from ..selection.selector import Candidate

DISCLAIMER = (
    "本报告由「主线雷达」基于历史数据自动生成，仅供研究与教育之用，"
    "不构成任何投资建议。股市有风险，决策与盈亏自负。"
)


class ReportBuilder:
    """把逻辑链渲染成 Markdown/HTML 报告。"""

    def __init__(self, fmt: str = "markdown") -> None:
        self.fmt = fmt

    def build(
        self,
        regime: "RegimeState",
        theme_name: str,
        bottleneck: dict | None,
        candidates: list["Candidate"],
    ) -> str:
        """生成完整研究报告。

        阶段 7 用 Jinja2 模板，章节包含：市场状态 → 主题与产业链 →
        瓶颈环节 → 候选公司（含逐项理由与数据出处）→ 风险与免责。
        本骨架先返回一个最小 Markdown 摘要占位。
        """
        # TODO(阶段7): Jinja2 模板渲染、图表、数据出处标注。
        lines = [
            "# 主线雷达 · 研究报告（骨架占位）",
            "",
            f"- 市场状态：{regime}",
            f"- 主题：{theme_name}",
            f"- 瓶颈环节：{(bottleneck or {}).get('name', 'N/A')}",
            "",
            "## 候选公司",
        ]
        for c in candidates:
            lines.append(f"- {c.explain()}")
        lines += ["", "---", f"> {DISCLAIMER}"]
        return "\n".join(lines)
