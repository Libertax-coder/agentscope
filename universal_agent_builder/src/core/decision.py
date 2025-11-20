"""Decision data structure for tracking Master Agent's decision path"""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class Decision(BaseModel):
    """表示 Master Agent 的一次决策

    决策路径由一系列 Decision 组成，记录：
    - 为什么做这个决定（reasoning）
    - 执行了什么行动（action）
    - 得到了什么结果（result）
    - 产生了哪些文件（artifacts）
    """

    # 决策标识
    decision_id: str = Field(
        description="决策唯一标识符",
    )

    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="决策时间戳",
    )

    # 推理过程
    reasoning: str = Field(
        description="为什么选择这个工具/Agent 的推理过程",
    )

    # 行动类型和内容
    action_type: Literal["tool", "sub_agent_independent", "sub_agent_interactive"] = (
        Field(
            description="行动类型：工具调用或 Sub-Agent 调用（独立/交互式）",
        )
    )

    action_name: str = Field(
        description="工具名或 Sub-Agent 名称",
    )

    action_input: dict[str, Any] = Field(
        description="行动的输入参数",
    )

    # 执行结果
    action_result: str = Field(
        description="执行结果摘要（不包含大量数据，只记录关键信息）",
    )

    action_status: Literal["success", "failed", "partial"] = Field(
        default="success",
        description="执行状态",
    )

    # 产出的文件
    artifacts_produced: list[str] = Field(
        default_factory=list,
        description="本次决策产生的文件路径列表",
    )

    # 可选：错误信息
    error_message: str | None = Field(
        default=None,
        description="如果失败，记录错误信息",
    )

    def to_summary(self) -> str:
        """生成决策摘要，用于 Prompt"""
        summary = f"""Decision #{self.decision_id} ({self.timestamp}):
Reasoning: {self.reasoning}
Action: {self.action_type} - {self.action_name}
Result: {self.action_result} [{self.action_status}]"""

        if self.artifacts_produced:
            summary += f"\nProduced: {', '.join(self.artifacts_produced)}"

        if self.error_message:
            summary += f"\nError: {self.error_message}"

        return summary

    def to_dict(self) -> dict[str, Any]:
        """转换为字典，用于序列化"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Decision":
        """从字典恢复"""
        return cls.model_validate(data)


class DecisionPath:
    """决策路径管理器

    管理一系列 Decision，提供：
    - 添加新决策
    - 查询历史决策
    - 生成摘要用于 Prompt
    """

    def __init__(self, max_history: int = 100):
        """初始化决策路径

        Args:
            max_history: 最大保留的决策数量（超过后会滚动删除最旧的）
        """
        self.decisions: list[Decision] = []
        self.max_history = max_history
        self._decision_counter = 0

    def add_decision(
        self,
        reasoning: str,
        action_type: str,
        action_name: str,
        action_input: dict[str, Any],
        action_result: str,
        action_status: str = "success",
        artifacts_produced: list[str] | None = None,
        error_message: str | None = None,
    ) -> Decision:
        """添加新决策

        Args:
            reasoning: 推理过程
            action_type: 行动类型
            action_name: 行动名称
            action_input: 输入参数
            action_result: 结果摘要
            action_status: 执行状态
            artifacts_produced: 产生的文件
            error_message: 错误信息

        Returns:
            Decision: 新创建的决策对象
        """
        self._decision_counter += 1
        decision = Decision(
            decision_id=f"D{self._decision_counter:04d}",
            reasoning=reasoning,
            action_type=action_type,  # type: ignore
            action_name=action_name,
            action_input=action_input,
            action_result=action_result,
            action_status=action_status,  # type: ignore
            artifacts_produced=artifacts_produced or [],
            error_message=error_message,
        )

        self.decisions.append(decision)

        # 保持历史记录在限制范围内
        if len(self.decisions) > self.max_history:
            self.decisions = self.decisions[-self.max_history :]

        return decision

    def get_recent_decisions(self, n: int = 5) -> list[Decision]:
        """获取最近的 n 个决策

        Args:
            n: 决策数量

        Returns:
            list[Decision]: 最近的决策列表
        """
        return self.decisions[-n:] if self.decisions else []

    def get_failed_decisions(self) -> list[Decision]:
        """获取所有失败的决策

        Returns:
            list[Decision]: 失败的决策列表
        """
        return [d for d in self.decisions if d.action_status == "failed"]

    def format_recent_for_prompt(self, n: int = 5) -> str:
        """格式化最近的决策用于 Prompt

        Args:
            n: 决策数量

        Returns:
            str: 格式化的决策摘要
        """
        recent = self.get_recent_decisions(n)
        if not recent:
            return "No previous decisions."

        summaries = [d.to_summary() for d in recent]
        return "\n\n".join(summaries)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "decisions": [d.to_dict() for d in self.decisions],
            "max_history": self.max_history,
            "decision_counter": self._decision_counter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionPath":
        """从字典恢复"""
        instance = cls(max_history=data["max_history"])
        instance.decisions = [
            Decision.from_dict(d) for d in data.get("decisions", [])
        ]
        instance._decision_counter = data.get("decision_counter", 0)
        return instance
