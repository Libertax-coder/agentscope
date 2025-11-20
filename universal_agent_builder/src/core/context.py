"""Master Agent Context Management

MasterContext 整合三部分信息：
1. Plan Context: 来自 Planner Agent 的计划
2. Decision Path: Master Agent 的决策历史
3. Artifacts: 沉淀的文件资源
"""

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .decision import DecisionPath
from .artifact_manager import ArtifactManager


class PlanContext(BaseModel):
    """计划上下文（来自 Planner Agent）"""

    plan_id: str | None = Field(default=None, description="计划 ID")

    plan_name: str | None = Field(default=None, description="计划名称")

    plan_description: str | None = Field(default=None, description="计划描述")

    current_subtask: str | None = Field(default=None, description="当前子任务")

    current_subtask_idx: int | None = Field(default=None, description="当前子任务索引")

    progress: str = Field(default="Not started", description="进度描述")

    plan_summary: str | None = Field(
        default=None,
        description="计划的简洁摘要（用于 Prompt）",
    )

    def is_active(self) -> bool:
        """是否有活跃的计划"""
        return self.plan_id is not None

    def to_prompt_text(self) -> str:
        """生成用于 Prompt 的文本"""
        if not self.is_active():
            return "No active plan. Waiting for task initialization."

        return f"""## Current Plan
Plan: {self.plan_name}
Description: {self.plan_description}
Current Subtask: {self.current_subtask}
Progress: {self.progress}

{self.plan_summary or ''}
"""


class MasterContext:
    """Master Agent 的完整上下文

    三部分组成：
    1. plan_context: 当前计划和目标
    2. decision_path: 决策历史
    3. artifact_manager: 文件索引
    """

    def __init__(self, session_dir: str | Path):
        """初始化 Master Context

        Args:
            session_dir: Session 目录路径
        """
        self.session_dir = Path(session_dir)
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir(parents=True, exist_ok=True)

        # Part 1: Plan Context
        self.plan_context = PlanContext()

        # Part 2: Decision Path
        self.decision_path = DecisionPath(max_history=100)

        # Part 3: Artifact Manager
        self.artifact_manager = ArtifactManager(session_dir=session_dir)

        # 加载已有的上下文
        self._load_context()

    def _load_context(self):
        """加载已保存的上下文"""
        # 加载 plan context
        plan_file = self.context_dir / "plan.json"
        if plan_file.exists():
            try:
                with open(plan_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.plan_context = PlanContext.model_validate(data)
            except Exception as e:
                print(f"Warning: Failed to load plan context: {e}")

        # 加载 decision path
        decision_file = self.context_dir / "decision_path.json"
        if decision_file.exists():
            try:
                with open(decision_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.decision_path = DecisionPath.from_dict(data)
            except Exception as e:
                print(f"Warning: Failed to load decision path: {e}")

        # artifact_manager 在初始化时自动加载索引

    def save_context(self):
        """保存上下文到文件"""
        # 保存 plan context
        plan_file = self.context_dir / "plan.json"
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(self.plan_context.model_dump(), f, indent=2, ensure_ascii=False)

        # 保存 decision path
        decision_file = self.context_dir / "decision_path.json"
        with open(decision_file, "w", encoding="utf-8") as f:
            json.dump(self.decision_path.to_dict(), f, indent=2, ensure_ascii=False)

        # artifact_manager 在 register_artifact 时自动保存

    def update_plan_context(
        self,
        plan_id: str | None = None,
        plan_name: str | None = None,
        plan_description: str | None = None,
        current_subtask: str | None = None,
        current_subtask_idx: int | None = None,
        progress: str | None = None,
        plan_summary: str | None = None,
    ):
        """更新计划上下文

        Args:
            plan_id: 计划 ID
            plan_name: 计划名称
            plan_description: 计划描述
            current_subtask: 当前子任务
            current_subtask_idx: 当前子任务索引
            progress: 进度描述
            plan_summary: 计划摘要
        """
        if plan_id is not None:
            self.plan_context.plan_id = plan_id
        if plan_name is not None:
            self.plan_context.plan_name = plan_name
        if plan_description is not None:
            self.plan_context.plan_description = plan_description
        if current_subtask is not None:
            self.plan_context.current_subtask = current_subtask
        if current_subtask_idx is not None:
            self.plan_context.current_subtask_idx = current_subtask_idx
        if progress is not None:
            self.plan_context.progress = progress
        if plan_summary is not None:
            self.plan_context.plan_summary = plan_summary

        self.save_context()

    def clear_plan_context(self):
        """清空计划上下文（计划完成或取消时）"""
        self.plan_context = PlanContext()
        self.save_context()

    def build_prompt_context(
        self,
        include_recent_decisions: int = 5,
        include_artifacts_max: int = 20,
        user_message: str = "",
    ) -> str:
        """构建完整的 Prompt 上下文

        Args:
            include_recent_decisions: 包含最近的决策数量
            include_artifacts_max: 包含的最大文件数
            user_message: 用户消息

        Returns:
            str: 格式化的 Prompt 上下文
        """
        sections = []

        # Part 1: Plan Context
        sections.append("=" * 60)
        sections.append("PART 1: CURRENT PLAN")
        sections.append("=" * 60)
        sections.append(self.plan_context.to_prompt_text())

        # Part 2: Decision Path
        sections.append("\n" + "=" * 60)
        sections.append("PART 2: RECENT DECISION HISTORY")
        sections.append("=" * 60)
        sections.append(
            self.decision_path.format_recent_for_prompt(n=include_recent_decisions)
        )

        # Part 3: Artifacts
        sections.append("\n" + "=" * 60)
        sections.append("PART 3: AVAILABLE ARTIFACTS")
        sections.append("=" * 60)
        sections.append(
            self.artifact_manager.format_index_for_prompt(max_items=include_artifacts_max)
        )

        # User Message
        if user_message:
            sections.append("\n" + "=" * 60)
            sections.append("USER MESSAGE")
            sections.append("=" * 60)
            sections.append(user_message)

        return "\n".join(sections)

    def get_stats(self) -> dict[str, Any]:
        """获取上下文统计信息"""
        return {
            "session_dir": str(self.session_dir),
            "has_active_plan": self.plan_context.is_active(),
            "total_decisions": len(self.decision_path.decisions),
            "failed_decisions": len(self.decision_path.get_failed_decisions()),
            "artifacts": self.artifact_manager.get_stats(),
        }

    def __repr__(self) -> str:
        """字符串表示"""
        stats = self.get_stats()
        return (
            f"MasterContext(\n"
            f"  session_dir={stats['session_dir']},\n"
            f"  active_plan={stats['has_active_plan']},\n"
            f"  decisions={stats['total_decisions']},\n"
            f"  artifacts={stats['artifacts']['total_artifacts']}\n"
            f")"
        )
