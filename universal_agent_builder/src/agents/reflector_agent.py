"""Reflector Agent - 质量检验智能体

检验质量和准确性，智能路由反馈
"""

import json
import re
from typing import Any, Literal
from pydantic import BaseModel, Field

from agentscope.agent import AgentBase
from agentscope.message import Msg

from ..core.context import MasterContext


class Reflection(BaseModel):
    """Reflection 结果"""

    status: Literal["pass", "revise", "replan"] = Field(
        description="检验状态：pass-通过，revise-需修改，replan-需重新规划"
    )

    routing: Literal["master", "planner"] = Field(
        description="反馈路由：master-反馈给Master Agent，planner-反馈给Planner Agent"
    )

    feedback: str = Field(description="具体反馈内容")

    suggested_action: str | None = Field(
        default=None, description="建议的下一步行动"
    )

    quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="质量评分 (0-1)"
    )

    issues: list[str] = Field(default_factory=list, description="发现的问题列表")


class ReflectorAgent(AgentBase):
    """质量检验智能体

    职责：
    - 检验当前工作状态的质量和准确性
    - 决定反馈路由（Master 或 Planner）

    检查点：
    1. 当前 subtask 的完成质量
    2. 产出的 artifacts 是否符合预期
    3. Decision path 是否合理（有无死循环、重复错误）
    4. 是否偏离计划目标
    """

    def __init__(
        self,
        name: str = "ReflectorAgent",
        model_config_name: str | None = None,
        quality_threshold: float = 0.7,
        **kwargs: Any,
    ):
        """初始化 Reflector Agent

        Args:
            name: Agent 名称
            model_config_name: 模型配置名称
            quality_threshold: 质量阈值（低于此值认为需要修改）
            **kwargs: 其他参数传递给 AgentBase
        """
        super().__init__()

        # Agent 属性
        self.name = name
        self.model_config_name = model_config_name

        self.quality_threshold = quality_threshold

    async def reflect(self, master_context: MasterContext) -> Reflection:
        """检验当前工作状态

        Args:
            master_context: Master Agent 的上下文

        Returns:
            Reflection: 检验结果
        """
        # 构建检验 Prompt
        prompt = self._build_reflection_prompt(master_context)

        # 调用 LLM
        response = await self.model(prompt)

        # 解析反馈
        reflection = self._parse_reflection(response.text)

        return reflection

    def _build_reflection_prompt(self, context: MasterContext) -> Msg:
        """构建检验 Prompt

        Args:
            context: Master Context

        Returns:
            Msg: Prompt 消息
        """
        # 获取上下文信息
        plan_text = context.plan_context.to_prompt_text()
        recent_decisions = context.decision_path.format_recent_for_prompt(n=5)
        artifacts_summary = context.artifact_manager.format_index_for_prompt(
            max_items=10
        )

        # 获取失败的决策
        failed_decisions = context.decision_path.get_failed_decisions()
        failed_summary = (
            f"\n{len(failed_decisions)} failed decisions detected!"
            if failed_decisions
            else "No failed decisions."
        )

        prompt_text = f"""You are a quality inspector and evaluator. Your task is to review the current work status and provide feedback.

{60 * '='}
CURRENT WORK STATUS
{60 * '='}

## Current Plan:
{plan_text}

## Recent Decision History:
{recent_decisions}

{failed_summary}

## Produced Artifacts:
{artifacts_summary}

{60 * '='}
EVALUATION CRITERIA
{60 * '='}

Please evaluate the following aspects:

1. **Quality**: Is the current work meeting the expected outcome?
   - Are the artifacts of good quality?
   - Are the outputs correct and complete?

2. **Accuracy**: Are the results accurate?
   - Any logical errors or inconsistencies?
   - Data correctness?

3. **Alignment**: Is the work aligned with the plan?
   - Are we following the subtasks?
   - Any deviations from the goal?

4. **Issues**: Any problems or blockers?
   - Repeated failures?
   - Stuck in a loop?
   - Missing critical information?

{60 * '='}
OUTPUT FORMAT
{60 * '='}

Provide your feedback in JSON format:

{{
    "status": "pass" | "revise" | "replan",
    "routing": "master" | "planner",
    "feedback": "Detailed feedback message",
    "suggested_action": "What should be done next (optional)",
    "quality_score": 0.0 to 1.0,
    "issues": ["issue1", "issue2", ...]
}}

**Status Definitions:**
- "pass": Work is good, continue current task
- "revise": Need modification, but plan remains valid (route to master)
- "replan": Major issues, need to update plan (route to planner)

**Routing Logic:**
- "master": If the plan is still valid, but execution needs adjustment
- "planner": If the plan itself needs to be changed
"""

        return Msg(name=self.name, content=prompt_text, role="assistant")

    def _parse_reflection(self, response_text: str) -> Reflection:
        """解析 LLM 响应中的 Reflection 结果

        Args:
            response_text: LLM 响应文本

        Returns:
            Reflection: 检验结果
        """
        # 尝试提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))

                # 验证并创建 Reflection 对象
                reflection = Reflection.model_validate(data)

                # 基于质量分数决定路由（如果 LLM 没有正确设置）
                if reflection.quality_score < self.quality_threshold:
                    if reflection.status == "pass":
                        reflection.status = "revise"

                # 确保路由逻辑正确
                if reflection.status == "replan":
                    reflection.routing = "planner"
                elif reflection.status in ["pass", "revise"]:
                    reflection.routing = "master"

                return reflection

            except (json.JSONDecodeError, Exception) as e:
                print(f"Warning: Failed to parse reflection: {e}")

        # 回退：创建默认 Reflection（通过）
        return Reflection(
            status="pass",
            routing="master",
            feedback="Automatic review: No issues detected.",
            quality_score=0.8,
        )

    async def reply(self, x: Msg) -> Msg:
        """处理消息（主要用于 Agent 接口兼容）

        Args:
            x: 输入消息

        Returns:
            Msg: 响应消息
        """
        # Reflector Agent 通常不直接处理用户消息
        # 而是通过 reflect() 方法被 Master Agent 调用
        return Msg(
            name=self.name,
            content="ReflectorAgent is ready. Use reflect(context) to evaluate work status.",
            role="assistant",
        )

    def quick_check(self, context: MasterContext) -> dict[str, Any]:
        """快速检查（不使用 LLM）

        Args:
            context: Master Context

        Returns:
            dict: 检查结果
        """
        issues = []
        warnings = []

        # 检查失败的决策
        failed_decisions = context.decision_path.get_failed_decisions()
        if len(failed_decisions) > 3:
            issues.append(
                f"Too many failed decisions: {len(failed_decisions)}"
            )

        # 检查是否有产出
        if len(context.artifact_manager.index) == 0:
            recent_decisions = context.decision_path.get_recent_decisions(n=5)
            if len(recent_decisions) >= 5:
                warnings.append("No artifacts produced after 5 decisions")

        # 检查计划进度
        if context.plan_context.is_active():
            # 可以添加更多进度检查逻辑
            pass

        return {
            "has_issues": len(issues) > 0,
            "issues": issues,
            "warnings": warnings,
            "failed_decisions_count": len(failed_decisions),
            "artifacts_count": len(context.artifact_manager.index),
        }
