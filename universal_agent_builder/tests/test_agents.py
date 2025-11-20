"""Tests for Core Agents (Planner, Master, Reflector)"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock

import pytest

from src.agents.planner_agent import PlannerAgent
from src.agents.master_agent import MasterAgent
from src.agents.reflector_agent import ReflectorAgent, Reflection
from src.core.context import MasterContext


class TestPlannerAgent:
    """测试 Planner Agent"""

    @pytest.fixture
    def temp_session_dir(self):
        """创建临时 session 目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_plan_notebook(self):
        """Mock PlanNotebook"""
        notebook = Mock()
        notebook.current_plan = None
        notebook.create_plan = AsyncMock()
        notebook.revise_current_plan = AsyncMock()
        notebook.finish_plan = AsyncMock()
        notebook.recover_historical_plan = AsyncMock()
        notebook.update_subtask_state = AsyncMock()
        notebook.finish_subtask = AsyncMock()
        return notebook

    def test_planner_agent_initialization(self, mock_plan_notebook):
        """测试 Planner Agent 初始化"""
        planner = PlannerAgent(
            name="TestPlanner",
            plan_notebook=mock_plan_notebook,
        )

        assert planner.name == "TestPlanner"
        assert planner.plan_notebook is mock_plan_notebook
        assert isinstance(planner.plan_history_stack, list)

    @pytest.mark.asyncio
    async def test_get_current_plan_context_no_plan(self, mock_plan_notebook):
        """测试获取计划上下文（无计划）"""
        planner = PlannerAgent(plan_notebook=mock_plan_notebook)

        plan_context = planner.get_current_plan_context()

        assert plan_context.plan_id is None
        assert not plan_context.is_active()

    @pytest.mark.asyncio
    async def test_get_current_plan_context_with_plan(self, mock_plan_notebook):
        """测试获取计划上下文（有计划）"""
        # Mock 一个计划
        from agentscope.plan import Plan, SubTask

        mock_plan = Plan(
            name="Test Plan",
            description="Test description",
            expected_outcome="Test outcome",
            subtasks=[
                SubTask(
                    name="Task 1",
                    description="First task",
                    expected_outcome="Task 1 done",
                    state="in_progress",
                ),
                SubTask(
                    name="Task 2",
                    description="Second task",
                    expected_outcome="Task 2 done",
                    state="todo",
                ),
            ],
        )

        mock_plan_notebook.current_plan = mock_plan
        planner = PlannerAgent(plan_notebook=mock_plan_notebook)

        plan_context = planner.get_current_plan_context()

        assert plan_context.plan_id == mock_plan.id
        assert plan_context.plan_name == "Test Plan"
        assert plan_context.current_subtask == "Task 1"
        assert plan_context.current_subtask_idx == 0
        assert "1/2" in plan_context.progress or "0/2" in plan_context.progress

    @pytest.mark.asyncio
    async def test_mark_subtask_progress_done(self, mock_plan_notebook):
        """测试标记子任务完成"""
        from agentscope.tool import ToolResponse
        from agentscope.message import TextBlock

        mock_response = ToolResponse(
            content=[TextBlock(type="text", text="Subtask marked as done")]
        )
        mock_plan_notebook.finish_subtask.return_value = mock_response

        planner = PlannerAgent(plan_notebook=mock_plan_notebook)

        result = await planner.mark_subtask_progress(
            subtask_idx=0,
            state="done",
            outcome="Task completed successfully",
        )

        assert "done" in result or "Subtask marked" in result
        mock_plan_notebook.finish_subtask.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_subtask_progress_in_progress(self, mock_plan_notebook):
        """测试标记子任务进行中"""
        from agentscope.tool import ToolResponse
        from agentscope.message import TextBlock

        mock_response = ToolResponse(
            content=[
                TextBlock(type="text", text="Subtask marked as in_progress")
            ]
        )
        mock_plan_notebook.update_subtask_state.return_value = mock_response

        planner = PlannerAgent(plan_notebook=mock_plan_notebook)

        result = await planner.mark_subtask_progress(
            subtask_idx=0,
            state="in_progress",
        )

        assert "in_progress" in result or "Subtask marked" in result
        mock_plan_notebook.update_subtask_state.assert_called_once()


class TestMasterAgent:
    """测试 Master Agent"""

    @pytest.fixture
    def temp_session_dir(self):
        """创建临时 session 目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_planner(self):
        """Mock Planner Agent"""
        planner = Mock()
        planner.get_current_plan_context = Mock()

        from src.core.context import PlanContext

        planner.get_current_plan_context.return_value = PlanContext()
        return planner

    @pytest.fixture
    def mock_reflector(self):
        """Mock Reflector Agent"""
        reflector = Mock()
        reflector.reflect = AsyncMock()
        reflector.reflect.return_value = Reflection(
            status="pass",
            routing="master",
            feedback="All good",
            quality_score=0.9,
        )
        return reflector

    def test_master_agent_initialization(
        self, temp_session_dir, mock_planner, mock_reflector
    ):
        """测试 Master Agent 初始化"""
        master = MasterAgent(
            name="TestMaster",
            session_dir=temp_session_dir,
            planner_agent=mock_planner,
            reflector_agent=mock_reflector,
        )

        assert master.name == "TestMaster"
        assert master.session_dir == temp_session_dir
        assert master.planner is mock_planner
        assert master.reflector is mock_reflector
        assert isinstance(master.context, MasterContext)

    def test_master_agent_context_management(self, temp_session_dir):
        """测试 Master Agent 上下文管理"""
        master = MasterAgent(session_dir=temp_session_dir)

        # 检查 Context 是否正确初始化
        assert master.context.session_dir == temp_session_dir
        assert master.context.plan_context is not None
        assert master.context.decision_path is not None
        assert master.context.artifact_manager is not None

    def test_master_agent_tools_and_subagents(self, temp_session_dir):
        """测试 Master Agent 工具和 Sub-Agent 管理"""
        # Mock 工具
        def mock_tool(**kwargs):
            return {"result": "success"}

        # Mock Sub-Agent
        mock_sub_agent = Mock()
        mock_sub_agent.reply = AsyncMock()
        from agentscope.message import Msg

        mock_sub_agent.reply.return_value = Msg(
            name="SubAgent", content="Done", role="assistant"
        )

        master = MasterAgent(
            session_dir=temp_session_dir,
            tools={"test_tool": mock_tool},
            sub_agents={"test_agent": mock_sub_agent},
        )

        assert "test_tool" in master.tools
        assert "test_agent" in master.sub_agents

    def test_should_reflect_frequency(self, temp_session_dir, mock_reflector):
        """测试 Reflection 触发频率"""
        master = MasterAgent(
            session_dir=temp_session_dir,
            reflector_agent=mock_reflector,
            enable_reflection=True,
            reflection_frequency=3,
        )

        # 前两次不触发
        master._decision_counter = 1
        assert not master._should_reflect()

        master._decision_counter = 2
        assert not master._should_reflect()

        # 第三次触发
        master._decision_counter = 3
        assert master._should_reflect()

    def test_should_reflect_disabled(self, temp_session_dir):
        """测试禁用 Reflection"""
        master = MasterAgent(
            session_dir=temp_session_dir,
            enable_reflection=False,
        )

        master._decision_counter = 3
        assert not master._should_reflect()

    def test_parse_action_from_response(self, temp_session_dir):
        """测试解析行动决策"""
        master = MasterAgent(session_dir=temp_session_dir)

        # 正确的 JSON
        response = """
        Here is my decision:
        {
            "reasoning": "Need to search for information",
            "action_type": "tool",
            "action_name": "web_search",
            "action_input": {"query": "test"}
        }
        """

        action = master._parse_action_from_response(response)

        assert action["reasoning"] == "Need to search for information"
        assert action["action_type"] == "tool"
        assert action["action_name"] == "web_search"
        assert action["action_input"]["query"] == "test"

    def test_parse_action_from_response_invalid(self, temp_session_dir):
        """测试解析无效响应（回退）"""
        master = MasterAgent(session_dir=temp_session_dir)

        response = "This is not a valid JSON response"

        action = master._parse_action_from_response(response)

        # 应该回退到默认行动
        assert action["action_type"] == "tool"
        assert action["action_name"] == "think"

    def test_get_stats(self, temp_session_dir):
        """测试获取统计信息"""
        master = MasterAgent(
            session_dir=temp_session_dir,
            tools={"tool1": lambda: None, "tool2": lambda: None},
            sub_agents={"agent1": Mock()},
        )

        stats = master.get_stats()

        assert "session_dir" in stats
        assert "context_stats" in stats
        assert "total_decisions" in stats
        assert len(stats["tools_available"]) == 2
        assert len(stats["sub_agents_available"]) == 1


class TestReflectorAgent:
    """测试 Reflector Agent"""

    @pytest.fixture
    def temp_session_dir(self):
        """创建临时 session 目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_reflector_agent_initialization(self):
        """测试 Reflector Agent 初始化"""
        reflector = ReflectorAgent(
            name="TestReflector",
            quality_threshold=0.8,
        )

        assert reflector.name == "TestReflector"
        assert reflector.quality_threshold == 0.8

    def test_parse_reflection_valid(self):
        """测试解析有效的 Reflection 响应"""
        reflector = ReflectorAgent()

        response = """
        {
            "status": "pass",
            "routing": "master",
            "feedback": "Work is good",
            "quality_score": 0.9,
            "issues": []
        }
        """

        reflection = reflector._parse_reflection(response)

        assert reflection.status == "pass"
        assert reflection.routing == "master"
        assert reflection.quality_score == 0.9

    def test_parse_reflection_needs_revision(self):
        """测试低质量分数自动调整状态"""
        reflector = ReflectorAgent(quality_threshold=0.7)

        response = """
        {
            "status": "pass",
            "routing": "master",
            "feedback": "Has issues",
            "quality_score": 0.5,
            "issues": ["issue1"]
        }
        """

        reflection = reflector._parse_reflection(response)

        # 质量分数低于阈值，应该调整为 revise
        assert reflection.status == "revise"

    def test_parse_reflection_replan_routing(self):
        """测试 replan 状态自动路由到 planner"""
        reflector = ReflectorAgent()

        response = """
        {
            "status": "replan",
            "routing": "master",
            "feedback": "Need to change plan",
            "quality_score": 0.3,
            "issues": ["major issue"]
        }
        """

        reflection = reflector._parse_reflection(response)

        # replan 应该路由到 planner
        assert reflection.routing == "planner"

    def test_parse_reflection_invalid_fallback(self):
        """测试无效响应回退"""
        reflector = ReflectorAgent()

        response = "This is not a valid JSON"

        reflection = reflector._parse_reflection(response)

        # 应该回退到默认（通过）
        assert reflection.status == "pass"
        assert reflection.routing == "master"
        assert reflection.quality_score > 0

    def test_quick_check_no_issues(self, temp_session_dir):
        """测试快速检查（无问题）"""
        reflector = ReflectorAgent()
        context = MasterContext(session_dir=temp_session_dir)

        # 添加一些正常决策
        context.decision_path.add_decision(
            reasoning="Test",
            action_type="tool",
            action_name="tool1",
            action_input={},
            action_result="OK",
            action_status="success",
        )

        result = reflector.quick_check(context)

        assert not result["has_issues"]
        assert len(result["issues"]) == 0

    def test_quick_check_too_many_failures(self, temp_session_dir):
        """测试快速检查（失败过多）"""
        reflector = ReflectorAgent()
        context = MasterContext(session_dir=temp_session_dir)

        # 添加 5 个失败的决策
        for i in range(5):
            context.decision_path.add_decision(
                reasoning=f"Test {i}",
                action_type="tool",
                action_name=f"tool{i}",
                action_input={},
                action_result="Failed",
                action_status="failed",
                error_message="Error",
            )

        result = reflector.quick_check(context)

        assert result["has_issues"]
        assert result["failed_decisions_count"] == 5
        assert len(result["issues"]) > 0

    def test_quick_check_no_artifacts_warning(self, temp_session_dir):
        """测试快速检查（无产出警告）"""
        reflector = ReflectorAgent()
        context = MasterContext(session_dir=temp_session_dir)

        # 添加 5 个决策但无产出
        for i in range(5):
            context.decision_path.add_decision(
                reasoning=f"Test {i}",
                action_type="tool",
                action_name=f"tool{i}",
                action_input={},
                action_result="OK",
                action_status="success",
            )

        result = reflector.quick_check(context)

        # 应该有警告
        assert len(result["warnings"]) > 0
        assert result["artifacts_count"] == 0
