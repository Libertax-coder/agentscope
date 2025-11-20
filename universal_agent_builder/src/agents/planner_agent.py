"""Planner Agent - 计划管理智能体

封装 PlanNotebook 交互，自动管理计划生命周期
"""

from typing import Any
from agentscope.agent import AgentBase
from agentscope.plan import PlanNotebook, Plan, SubTask
from agentscope.message import Msg

from ..core.context import PlanContext


class PlannerAgent(AgentBase):
    """计划管理智能体

    职责：
    - PlanNotebook 的代理层，封装所有 PlanNotebook 交互
    - 自动管理计划生命周期（初始化、更新、版本控制）
    - 响应用户打断和 Reflector 反馈
    - 提供简洁的计划上下文给 Master Agent

    不直接暴露 PlanNotebook 给 Master Agent
    """

    def __init__(
        self,
        name: str = "PlannerAgent",
        model_config_name: str | None = None,
        plan_notebook: PlanNotebook | None = None,
        **kwargs: Any,
    ):
        """初始化 Planner Agent

        Args:
            name: Agent 名称
            model_config_name: 模型配置名称
            plan_notebook: PlanNotebook 实例（如果为 None 会自动创建）
            **kwargs: 其他参数传递给 AgentBase
        """
        super().__init__()

        # Agent 属性
        self.name = name
        self.model_config_name = model_config_name

        # PlanNotebook 实例
        self.plan_notebook = plan_notebook or PlanNotebook()

        # 本地计划版本栈（用于快速回滚）
        self.plan_history_stack: list[str] = []  # 存储 plan_id

    async def initialize_plan(
        self,
        user_requirement: str,
        use_llm: bool = True,
    ) -> tuple[Plan | None, str]:
        """基于用户需求初始化计划

        Args:
            user_requirement: 用户需求描述
            use_llm: 是否使用 LLM 生成计划（False 则返回建议，由调用者生成）

        Returns:
            tuple[Plan | None, str]: (计划对象, 状态消息)
        """
        if use_llm:
            # 使用 LLM 分析需求并生成计划
            prompt = self._build_plan_generation_prompt(user_requirement)
            response = await self.model(prompt)

            # 解析 LLM 输出的计划结构
            plan_data = self._parse_plan_from_response(response.text)

            # 创建计划
            result = await self.plan_notebook.create_plan(
                name=plan_data["name"],
                description=plan_data["description"],
                expected_outcome=plan_data["expected_outcome"],
                subtasks=plan_data["subtasks"],
            )

            if self.plan_notebook.current_plan:
                # 记录到历史栈
                self.plan_history_stack.append(
                    self.plan_notebook.current_plan.id
                )

                return (
                    self.plan_notebook.current_plan,
                    f"Plan '{self.plan_notebook.current_plan.name}' created successfully.",
                )
            else:
                return None, "Failed to create plan."
        else:
            # 不使用 LLM，返回建议
            return (
                None,
                f"Requirement received: {user_requirement}\n"
                "Please use create_plan() to manually create a plan.",
            )

    def _build_plan_generation_prompt(self, user_requirement: str) -> Msg:
        """构建计划生成的 Prompt"""
        prompt_text = f"""You are a planning expert. Based on the user's requirement, create a detailed plan.

User Requirement:
{user_requirement}

Please analyze the requirement and create a plan with the following structure:

1. Plan Name: A concise name (max 10 words)
2. Description: Clear description including constraints, target, and outcome
3. Expected Outcome: Specific, concrete, and measurable outcome
4. Subtasks: A list of sequential subtasks, each with:
   - name: Concise name (max 10 words)
   - description: Clear, specific, and measurable
   - expected_outcome: What should be achieved

Output in JSON format:
{{
    "name": "Plan name",
    "description": "Plan description",
    "expected_outcome": "Expected outcome",
    "subtasks": [
        {{
            "name": "Subtask 1",
            "description": "Subtask 1 description",
            "expected_outcome": "Subtask 1 outcome"
        }},
        ...
    ]
}}
"""
        return Msg(name=self.name, content=prompt_text, role="assistant")

    def _parse_plan_from_response(self, response_text: str) -> dict[str, Any]:
        """解析 LLM 响应中的计划结构

        Args:
            response_text: LLM 响应文本

        Returns:
            dict: 计划数据
        """
        import json
        import re

        # 尝试提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            try:
                plan_data = json.loads(json_match.group(0))

                # 转换 subtasks 为 SubTask 对象
                subtasks = [
                    SubTask(**task) for task in plan_data.get("subtasks", [])
                ]
                plan_data["subtasks"] = subtasks

                return plan_data
            except json.JSONDecodeError:
                pass

        # 回退：创建默认计划
        return {
            "name": "User Task Plan",
            "description": response_text[:200],
            "expected_outcome": "Complete the user's requirement",
            "subtasks": [
                SubTask(
                    name="Analyze requirement",
                    description="Understand and analyze the user's requirement",
                    expected_outcome="Clear understanding of the task",
                ),
                SubTask(
                    name="Execute task",
                    description="Execute the main task",
                    expected_outcome="Task completed successfully",
                ),
            ],
        }

    async def update_plan(
        self,
        feedback: dict[str, Any],
        use_llm: bool = True,
    ) -> tuple[Plan | None, str]:
        """基于反馈更新计划

        Args:
            feedback: 反馈信息，包含：
                - type: 'user_interrupt' | 'reflector_feedback'
                - message: 反馈内容
                - suggested_action: 建议的行动（可选）
            use_llm: 是否使用 LLM 决定如何更新

        Returns:
            tuple[Plan | None, str]: (更新后的计划, 状态消息)
        """
        feedback_type = feedback.get("type", "unknown")
        message = feedback.get("message", "")

        if use_llm:
            # 使用 LLM 决定如何更新计划
            prompt = self._build_plan_update_prompt(feedback)
            response = await self.model(prompt)

            # 解析 LLM 的决策
            action = self._parse_update_action(response.text)

            if action["type"] == "revise_subtask":
                # 修改特定子任务
                result = await self.plan_notebook.revise_current_plan(
                    subtask_idx=action["subtask_idx"],
                    action=action["action"],  # 'add', 'revise', 'delete'
                    subtask=action.get("subtask"),
                )
                return (
                    self.plan_notebook.current_plan,
                    f"Plan updated: {result.content[0].text}",
                )

            elif action["type"] == "recreate":
                # 重新创建计划
                if self.plan_notebook.current_plan:
                    await self.plan_notebook.finish_plan(
                        state="abandoned",
                        outcome="Plan replaced due to feedback",
                    )

                # 创建新计划
                return await self.initialize_plan(
                    user_requirement=message, use_llm=True
                )

            else:
                return self.plan_notebook.current_plan, "No update needed."

        else:
            return (
                self.plan_notebook.current_plan,
                f"Feedback received ({feedback_type}): {message}",
            )

    def _build_plan_update_prompt(self, feedback: dict[str, Any]) -> Msg:
        """构建计划更新的 Prompt"""
        current_plan_str = self._format_current_plan()

        prompt_text = f"""You are a planning expert. Based on the feedback, decide how to update the current plan.

Current Plan:
{current_plan_str}

Feedback:
Type: {feedback.get('type')}
Message: {feedback.get('message')}

Decide one of the following actions:
1. revise_subtask: Modify/add/delete a specific subtask
2. recreate: Abandon current plan and create a new one
3. no_change: No update needed

Output in JSON format:
{{
    "type": "revise_subtask" | "recreate" | "no_change",
    "subtask_idx": <index> (if revise_subtask),
    "action": "add" | "revise" | "delete" (if revise_subtask),
    "subtask": {{...}} (if add/revise),
    "reasoning": "Why this action"
}}
"""
        return Msg(name=self.name, content=prompt_text, role="assistant")

    def _parse_update_action(self, response_text: str) -> dict[str, Any]:
        """解析更新行动"""
        import json
        import re

        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            try:
                action_data = json.loads(json_match.group(0))

                # 转换 subtask 为 SubTask 对象
                if "subtask" in action_data and action_data["subtask"]:
                    action_data["subtask"] = SubTask(**action_data["subtask"])

                return action_data
            except json.JSONDecodeError:
                pass

        # 默认：不更新
        return {"type": "no_change"}

    async def rollback_plan(self, steps: int = 1) -> tuple[Plan | None, str]:
        """回滚到历史版本

        Args:
            steps: 回滚步数（默认 1，即上一个版本）

        Returns:
            tuple[Plan | None, str]: (回滚后的计划, 状态消息)
        """
        if len(self.plan_history_stack) < steps:
            return (
                self.plan_notebook.current_plan,
                f"Cannot rollback {steps} steps. Only {len(self.plan_history_stack)} versions available.",
            )

        # 获取目标版本的 plan_id
        target_plan_id = self.plan_history_stack[-(steps)]

        # 使用 PlanNotebook 的 recover_historical_plan
        result = await self.plan_notebook.recover_historical_plan(target_plan_id)

        # 更新历史栈
        self.plan_history_stack = self.plan_history_stack[:-steps]

        return (
            self.plan_notebook.current_plan,
            f"Plan rolled back {steps} step(s): {result.content[0].text}",
        )

    async def mark_subtask_progress(
        self,
        subtask_idx: int,
        state: str,
        outcome: str | None = None,
    ) -> str:
        """标记子任务进度

        Args:
            subtask_idx: 子任务索引
            state: 状态（'in_progress', 'done', 'abandoned'）
            outcome: 实际结果（如果是 'done'）

        Returns:
            str: 状态消息
        """
        if state == "done" and outcome:
            result = await self.plan_notebook.finish_subtask(
                subtask_idx=subtask_idx,
                outcome=outcome,
            )
        else:
            result = await self.plan_notebook.update_subtask_state(
                subtask_idx=subtask_idx,
                state=state,  # type: ignore
            )

        # 兼容处理：支持 TextBlock 对象或字典
        content = result.content[0]
        if hasattr(content, 'text'):
            return content.text
        elif isinstance(content, dict):
            return content.get('text', str(content))
        else:
            return str(content)

    def get_current_plan_context(self) -> PlanContext:
        """获取当前计划的上下文表示（给 Master Agent）

        Returns:
            PlanContext: 计划上下文对象
        """
        if not self.plan_notebook.current_plan:
            return PlanContext()

        plan = self.plan_notebook.current_plan

        # 找到当前正在进行的子任务
        current_subtask = None
        current_subtask_idx = None
        for idx, subtask in enumerate(plan.subtasks):
            if subtask.state == "in_progress":
                current_subtask = subtask.name
                current_subtask_idx = idx
                break

        # 如果没有正在进行的，找第一个未完成的
        if current_subtask is None:
            for idx, subtask in enumerate(plan.subtasks):
                if subtask.state == "todo":
                    current_subtask = subtask.name
                    current_subtask_idx = idx
                    break

        # 计算进度
        done_count = sum(1 for st in plan.subtasks if st.state == "done")
        total_count = len(plan.subtasks)
        progress = f"{done_count}/{total_count} subtasks completed"

        # 生成简洁摘要
        plan_summary = self._format_current_plan()

        return PlanContext(
            plan_id=plan.id,
            plan_name=plan.name,
            plan_description=plan.description,
            current_subtask=current_subtask,
            current_subtask_idx=current_subtask_idx,
            progress=progress,
            plan_summary=plan_summary,
        )

    def _format_current_plan(self) -> str:
        """格式化当前计划为简洁文本"""
        if not self.plan_notebook.current_plan:
            return "No active plan"

        plan = self.plan_notebook.current_plan
        lines = [
            f"Plan: {plan.name}",
            f"Description: {plan.description}",
            f"Expected Outcome: {plan.expected_outcome}",
            "\nSubtasks:",
        ]

        for idx, subtask in enumerate(plan.subtasks):
            status_icon = {
                "todo": "○",
                "in_progress": "◐",
                "done": "●",
                "abandoned": "✗",
            }.get(subtask.state, "?")

            lines.append(f"  {idx}. {status_icon} {subtask.name}")
            if subtask.state == "in_progress":
                lines.append(f"     → {subtask.description}")

        return "\n".join(lines)

    async def reply(self, x: Msg) -> Msg:
        """处理消息（主要用于 Agent 接口兼容）"""
        # Planner Agent 通常不直接处理用户消息
        # 而是通过 initialize_plan、update_plan 等方法被调用
        return Msg(
            name=self.name,
            content="PlannerAgent is ready. Use initialize_plan() or update_plan() to manage plans.",
            role="assistant",
        )
