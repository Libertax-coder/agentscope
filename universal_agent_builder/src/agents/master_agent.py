"""Master Agent - 核心决策智能体

基于 Context 预测下一步行动，协调整体工作流
"""

import json
from typing import Any, Callable, Coroutine
from pathlib import Path

from agentscope.agent import AgentBase
from agentscope.message import Msg

from ..core.context import MasterContext
from .planner_agent import PlannerAgent


class MasterAgent(AgentBase):
    """主控智能体

    职责：
    - 核心决策者，基于 Context 预测下一步行动
    - 调用工具或 Sub-Agent
    - 维护决策路径历史

    Context 组成（三部分）：
    1. Plan: 来自 Planner Agent 的目标导向计划
    2. Decision Path: Reasoning + Acting 历史
    3. Artifacts: 沉淀的文件资源（文件系统）

    使用较小模型（如 GPT-4o-mini），专注于决策
    """

    def __init__(
        self,
        name: str = "MasterAgent",
        model_config_name: str | None = None,
        session_dir: str | Path | None = None,
        planner_agent: PlannerAgent | None = None,
        reflector_agent: "ReflectorAgent | None" = None,
        tools: dict[str, Callable] | None = None,
        sub_agents: dict[str, AgentBase] | None = None,
        enable_reflection: bool = True,
        reflection_frequency: int = 3,  # 每 N 个决策触发一次 Reflection
        **kwargs: Any,
    ):
        """初始化 Master Agent

        Args:
            name: Agent 名称
            model_config_name: 模型配置名称（建议使用较小的模型）
            session_dir: Session 目录路径
            planner_agent: Planner Agent 实例
            reflector_agent: Reflector Agent 实例
            tools: 可用的工具函数字典
            sub_agents: Sub-Agent 字典 (key: agent_name, value: agent_instance)
            enable_reflection: 是否启用 Reflector
            reflection_frequency: Reflection 触发频率
            **kwargs: 其他参数传递给 AgentBase
        """
        super().__init__()

        # Agent 属性
        self.name = name
        self.model_config_name = model_config_name

        # Session 目录
        if session_dir is None:
            session_dir = Path.cwd() / "sessions" / "default_session"
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Context 管理
        self.context = MasterContext(session_dir=self.session_dir)

        # Agent 和工具
        self.planner = planner_agent
        self.reflector = reflector_agent
        self.tools = tools or {}
        self.sub_agents = sub_agents or {}

        # Reflection 配置
        self.enable_reflection = enable_reflection
        self.reflection_frequency = reflection_frequency
        self._decision_counter = 0

    async def reply(self, x: Msg) -> Msg:
        """主循环：处理用户消息并返回响应

        Args:
            x: 用户消息

        Returns:
            Msg: Agent 响应
        """
        user_message = x.content

        # 1. 如果没有活跃计划，先初始化计划
        if self.planner and not self.context.plan_context.is_active():
            plan, msg = await self.planner.initialize_plan(
                user_requirement=user_message,
                use_llm=True,
            )
            if plan:
                # 更新 Context 中的计划
                plan_context = self.planner.get_current_plan_context()
                self.context.update_plan_context(
                    plan_id=plan_context.plan_id,
                    plan_name=plan_context.plan_name,
                    plan_description=plan_context.plan_description,
                    current_subtask=plan_context.current_subtask,
                    current_subtask_idx=plan_context.current_subtask_idx,
                    progress=plan_context.progress,
                    plan_summary=plan_context.plan_summary,
                )

                return Msg(
                    name=self.name,
                    content=f"Plan initialized: {msg}\n\nStarting execution...",
                    role="assistant",
                )

        # 2. 更新 Context（从 Planner 获取最新计划状态）
        await self._update_context()

        # 3. 构建 Prompt
        prompt = self._build_prompt(user_message)

        # 4. LLM 预测下一步行动
        action = await self._predict_next_action(prompt)

        # 5. 执行行动
        result = await self._execute_action(action)

        # 6. 记录到 Decision Path
        self._record_decision(action, result)

        # 7. 可选：触发 Reflector 检验
        if self._should_reflect():
            reflection_result = await self._handle_reflection()
            if reflection_result:
                result = f"{result}\n\n[Reflection]: {reflection_result}"

        return Msg(
            name=self.name,
            content=result,
            role="assistant",
        )

    async def _update_context(self):
        """更新 Context（从 Planner 获取最新状态）"""
        if self.planner:
            plan_context = self.planner.get_current_plan_context()
            self.context.update_plan_context(
                plan_id=plan_context.plan_id,
                plan_name=plan_context.plan_name,
                plan_description=plan_context.plan_description,
                current_subtask=plan_context.current_subtask,
                current_subtask_idx=plan_context.current_subtask_idx,
                progress=plan_context.progress,
                plan_summary=plan_context.plan_summary,
            )

    def _build_prompt(self, user_message: str) -> Msg:
        """基于三部分 Context 构建 Prompt

        Args:
            user_message: 用户消息

        Returns:
            Msg: 构建的 Prompt 消息
        """
        # 使用 MasterContext 构建完整上下文
        context_text = self.context.build_prompt_context(
            include_recent_decisions=5,
            include_artifacts_max=20,
            user_message=user_message,
        )

        # 添加决策指南
        decision_guide = self._build_decision_guide()

        prompt_text = f"""{context_text}

{decision_guide}

Based on the above context, predict the next action to take.
"""

        return Msg(name=self.name, content=prompt_text, role="assistant")

    def _build_decision_guide(self) -> str:
        """构建决策指南"""
        # 列出可用的工具
        tools_list = "\n".join(f"  - {name}" for name in self.tools.keys())

        # 列出可用的 Sub-Agent
        agents_list = "\n".join(f"  - {name}" for name in self.sub_agents.keys())

        guide = f"""
{60 * '='}
DECISION GUIDE
{60 * '='}

You have access to the following resources:

## Tools:
{tools_list if tools_list else "  (No tools available)"}

## Sub-Agents:
{agents_list if agents_list else "  (No sub-agents available)"}

## Output Format:
You must output your decision in the following JSON format:

{{
    "reasoning": "Why you choose this action",
    "action_type": "tool" | "sub_agent_independent" | "sub_agent_interactive",
    "action_name": "name of the tool or sub-agent",
    "action_input": {{
        // Input parameters for the action
    }}
}}

## Action Types:
- tool: Call a standalone tool function
- sub_agent_independent: Call a sub-agent without sharing context (simple task)
- sub_agent_interactive: Call a sub-agent with shared context (complex task)
"""
        return guide

    async def _predict_next_action(self, prompt: Msg) -> dict[str, Any]:
        """使用 LLM 预测下一步行动

        Args:
            prompt: 构建的 Prompt

        Returns:
            dict: 行动决策
        """
        response = await self.model(prompt)

        # 解析 LLM 输出的 JSON
        action = self._parse_action_from_response(response.text)

        return action

    def _parse_action_from_response(self, response_text: str) -> dict[str, Any]:
        """解析 LLM 响应中的行动决策

        Args:
            response_text: LLM 响应文本

        Returns:
            dict: 行动决策
        """
        import re

        # 尝试提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            try:
                action = json.loads(json_match.group(0))

                # 验证必需字段
                required_fields = ["reasoning", "action_type", "action_name", "action_input"]
                if all(field in action for field in required_fields):
                    return action
            except json.JSONDecodeError:
                pass

        # 回退：返回默认行动（继续思考）
        return {
            "reasoning": "Unable to parse action, need more information",
            "action_type": "tool",
            "action_name": "think",
            "action_input": {"thought": response_text},
        }

    async def _execute_action(self, action: dict[str, Any]) -> str:
        """执行工具或 Sub-Agent

        Args:
            action: 行动决策

        Returns:
            str: 执行结果摘要
        """
        action_type = action["action_type"]
        action_name = action["action_name"]
        action_input = action["action_input"]

        try:
            if action_type == "tool":
                return await self._call_tool(action_name, action_input)

            elif action_type == "sub_agent_independent":
                return await self._call_sub_agent_independent(
                    action_name, action_input
                )

            elif action_type == "sub_agent_interactive":
                return await self._call_sub_agent_interactive(
                    action_name, action_input
                )

            else:
                return f"Unknown action type: {action_type}"

        except Exception as e:
            return f"Error executing action: {str(e)}"

    async def _call_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """调用工具

        Args:
            tool_name: 工具名称
            tool_input: 工具输入

        Returns:
            str: 工具执行结果
        """
        if tool_name not in self.tools:
            return f"Tool '{tool_name}' not found"

        tool = self.tools[tool_name]

        # 调用工具
        result = await tool(**tool_input)

        # 如果工具返回文件路径，注册到 Artifact Manager
        if isinstance(result, dict) and "file_path" in result:
            self.context.artifact_manager.register_artifact(
                path=result["file_path"],
                artifact_type=result.get("type", "other"),
                summary=result.get("summary", "Tool output"),
                producer=tool_name,
            )

        return str(result)

    async def _call_sub_agent_independent(
        self, agent_name: str, agent_input: dict[str, Any]
    ) -> str:
        """独立调用 Sub-Agent（不共享完整 Context）

        Args:
            agent_name: Sub-Agent 名称
            agent_input: 输入参数

        Returns:
            str: Sub-Agent 执行结果
        """
        if agent_name not in self.sub_agents:
            return f"Sub-agent '{agent_name}' not found"

        sub_agent = self.sub_agents[agent_name]

        # 构建输入消息（只包含特定任务所需信息）
        input_msg = Msg(
            name=self.name,
            content=str(agent_input),
            role="user",
        )

        # 调用 Sub-Agent
        result = await sub_agent.reply(input_msg)

        return result.content

    async def _call_sub_agent_interactive(
        self, agent_name: str, agent_input: dict[str, Any]
    ) -> str:
        """交互式调用 Sub-Agent（共享 Context）

        Args:
            agent_name: Sub-Agent 名称
            agent_input: 输入参数

        Returns:
            str: Sub-Agent 执行结果
        """
        if agent_name not in self.sub_agents:
            return f"Sub-agent '{agent_name}' not found"

        sub_agent = self.sub_agents[agent_name]

        # 注入 Context（如果 Sub-Agent 支持）
        if hasattr(sub_agent, "set_shared_context"):
            sub_agent.set_shared_context(self.context)

        # 构建输入消息（包含上下文引用）
        input_msg = Msg(
            name=self.name,
            content=str(agent_input),
            role="user",
            metadata={"context": self.context},
        )

        # 调用 Sub-Agent
        result = await sub_agent.reply(input_msg)

        # 同步 Artifacts（Sub-Agent 可能产生了新文件）
        if hasattr(sub_agent, "get_produced_artifacts"):
            artifacts = sub_agent.get_produced_artifacts()
            for artifact in artifacts:
                self.context.artifact_manager.register_artifact(**artifact)

        return result.content

    def _record_decision(self, action: dict[str, Any], result: str):
        """记录决策到 Decision Path

        Args:
            action: 行动决策
            result: 执行结果
        """
        # 提取产生的文件（简化处理，实际应从结果中解析）
        artifacts_produced = []
        # TODO: 更智能地提取文件路径

        # 确定执行状态
        status = "success"
        error_message = None
        if "error" in result.lower() or "failed" in result.lower():
            status = "failed"
            error_message = result

        # 添加决策
        self.context.decision_path.add_decision(
            reasoning=action.get("reasoning", ""),
            action_type=action["action_type"],
            action_name=action["action_name"],
            action_input=action["action_input"],
            action_result=result[:500],  # 限制长度
            action_status=status,
            artifacts_produced=artifacts_produced,
            error_message=error_message,
        )

        # 保存 Context
        self.context.save_context()

        # 增加决策计数器
        self._decision_counter += 1

    def _should_reflect(self) -> bool:
        """判断是否应该触发 Reflection

        Returns:
            bool: 是否触发
        """
        if not self.enable_reflection or not self.reflector:
            return False

        # 每 N 个决策触发一次
        return self._decision_counter % self.reflection_frequency == 0

    async def _handle_reflection(self) -> str | None:
        """处理 Reflection

        Returns:
            str | None: Reflection 结果消息
        """
        if not self.reflector:
            return None

        # 调用 Reflector
        reflection = await self.reflector.reflect(self.context)

        # 根据 routing 处理反馈
        if reflection.routing == "master":
            # 反馈给 Master（自己）
            if reflection.status == "pass":
                return "Quality check passed. Continue."
            elif reflection.status == "revise":
                return f"Need revision: {reflection.feedback}"

        elif reflection.routing == "planner":
            # 反馈给 Planner 更新计划
            if self.planner:
                await self.planner.update_plan(
                    feedback={
                        "type": "reflector_feedback",
                        "message": reflection.feedback,
                        "suggested_action": reflection.suggested_action,
                    },
                    use_llm=True,
                )
                return f"Plan updated based on reflection: {reflection.feedback}"

        return None

    def get_stats(self) -> dict[str, Any]:
        """获取 Master Agent 统计信息

        Returns:
            dict: 统计信息
        """
        return {
            "session_dir": str(self.session_dir),
            "context_stats": self.context.get_stats(),
            "total_decisions": self._decision_counter,
            "tools_available": list(self.tools.keys()),
            "sub_agents_available": list(self.sub_agents.keys()),
        }
