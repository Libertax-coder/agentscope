"""Tests for Context Management System (Phase 1)"""

import json
import tempfile
from pathlib import Path

import pytest

from src.core.decision import Decision, DecisionPath
from src.core.artifact_manager import ArtifactManager, ArtifactMetadata
from src.core.context import MasterContext, PlanContext


class TestDecision:
    """测试 Decision 类"""

    def test_decision_creation(self):
        """测试创建决策"""
        decision = Decision(
            decision_id="D0001",
            reasoning="Need to fetch data from API",
            action_type="tool",
            action_name="web_search",
            action_input={"query": "AI agents 2024"},
            action_result="Found 10 relevant results",
            action_status="success",
            artifacts_produced=["data/search_results.json"],
        )

        assert decision.decision_id == "D0001"
        assert decision.action_type == "tool"
        assert decision.action_status == "success"
        assert len(decision.artifacts_produced) == 1

    def test_decision_summary(self):
        """测试决策摘要生成"""
        decision = Decision(
            decision_id="D0001",
            reasoning="Test reasoning",
            action_type="tool",
            action_name="test_tool",
            action_input={},
            action_result="Success",
        )

        summary = decision.to_summary()
        assert "D0001" in summary
        assert "test_tool" in summary
        assert "Success" in summary

    def test_decision_serialization(self):
        """测试决策序列化和反序列化"""
        decision = Decision(
            decision_id="D0001",
            reasoning="Test",
            action_type="tool",
            action_name="test",
            action_input={"key": "value"},
            action_result="OK",
        )

        # 序列化
        data = decision.to_dict()
        assert isinstance(data, dict)

        # 反序列化
        restored = Decision.from_dict(data)
        assert restored.decision_id == decision.decision_id
        assert restored.action_name == decision.action_name


class TestDecisionPath:
    """测试 DecisionPath 类"""

    def test_add_decision(self):
        """测试添加决策"""
        path = DecisionPath(max_history=10)

        decision = path.add_decision(
            reasoning="Test reasoning",
            action_type="tool",
            action_name="test_tool",
            action_input={"param": "value"},
            action_result="Success",
        )

        assert decision.decision_id == "D0001"
        assert len(path.decisions) == 1

    def test_get_recent_decisions(self):
        """测试获取最近决策"""
        path = DecisionPath()

        # 添加 5 个决策
        for i in range(5):
            path.add_decision(
                reasoning=f"Reason {i}",
                action_type="tool",
                action_name=f"tool_{i}",
                action_input={},
                action_result=f"Result {i}",
            )

        recent = path.get_recent_decisions(n=3)
        assert len(recent) == 3
        assert recent[-1].action_name == "tool_4"  # 最新的

    def test_get_failed_decisions(self):
        """测试获取失败决策"""
        path = DecisionPath()

        # 添加成功和失败的决策
        path.add_decision(
            reasoning="Success",
            action_type="tool",
            action_name="tool_1",
            action_input={},
            action_result="OK",
            action_status="success",
        )
        path.add_decision(
            reasoning="Failed",
            action_type="tool",
            action_name="tool_2",
            action_input={},
            action_result="Error",
            action_status="failed",
            error_message="Connection timeout",
        )

        failed = path.get_failed_decisions()
        assert len(failed) == 1
        assert failed[0].action_name == "tool_2"

    def test_format_for_prompt(self):
        """测试 Prompt 格式化"""
        path = DecisionPath()

        path.add_decision(
            reasoning="Test",
            action_type="tool",
            action_name="test_tool",
            action_input={},
            action_result="OK",
        )

        formatted = path.format_recent_for_prompt(n=5)
        assert "D0001" in formatted
        assert "test_tool" in formatted

    def test_serialization(self):
        """测试序列化"""
        path = DecisionPath()
        path.add_decision(
            reasoning="Test",
            action_type="tool",
            action_name="tool",
            action_input={},
            action_result="OK",
        )

        # 序列化
        data = path.to_dict()
        assert "decisions" in data
        assert "max_history" in data

        # 反序列化
        restored = DecisionPath.from_dict(data)
        assert len(restored.decisions) == 1
        assert restored.decisions[0].action_name == "tool"


class TestArtifactManager:
    """测试 ArtifactManager 类"""

    @pytest.fixture
    def temp_session_dir(self):
        """创建临时 session 目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_initialization(self, temp_session_dir):
        """测试初始化"""
        manager = ArtifactManager(session_dir=temp_session_dir)

        # 检查目录是否创建
        assert (temp_session_dir / "artifacts" / "documents").exists()
        assert (temp_session_dir / "artifacts" / "code").exists()
        assert (temp_session_dir / "artifacts" / "media").exists()
        assert (temp_session_dir / "artifacts" / "data").exists()
        assert (temp_session_dir / "context").exists()

    def test_register_artifact(self, temp_session_dir):
        """测试注册文件"""
        manager = ArtifactManager(session_dir=temp_session_dir)

        # 创建一个测试文件
        test_file = temp_session_dir / "artifacts" / "data" / "test.json"
        test_file.write_text('{"key": "value"}')

        # 注册文件
        artifact = manager.register_artifact(
            path=test_file,
            artifact_type="data",
            summary="Test data file",
            producer="test_agent",
            tags=["test", "json"],
        )

        assert artifact.type == "data"
        assert artifact.summary == "Test data file"
        assert "test" in artifact.tags

        # 验证索引
        assert len(manager.index) == 1
        assert "artifacts/data/test.json" in manager.index

    def test_get_artifact(self, temp_session_dir):
        """测试获取文件元信息"""
        manager = ArtifactManager(session_dir=temp_session_dir)

        manager.register_artifact(
            path="artifacts/test.md",
            artifact_type="document",
            summary="Test doc",
            producer="test",
        )

        artifact = manager.get_artifact("artifacts/test.md")
        assert artifact is not None
        assert artifact.type == "document"

    def test_get_artifacts_by_type(self, temp_session_dir):
        """测试按类型获取文件"""
        manager = ArtifactManager(session_dir=temp_session_dir)

        manager.register_artifact(
            path="artifacts/doc1.md", artifact_type="document", summary="Doc 1", producer="test"
        )
        manager.register_artifact(
            path="artifacts/code1.py", artifact_type="code", summary="Code 1", producer="test"
        )
        manager.register_artifact(
            path="artifacts/doc2.md", artifact_type="document", summary="Doc 2", producer="test"
        )

        docs = manager.get_artifacts_by_type("document")
        assert len(docs) == 2

        code = manager.get_artifacts_by_type("code")
        assert len(code) == 1

    def test_search_artifacts(self, temp_session_dir):
        """测试搜索文件"""
        manager = ArtifactManager(session_dir=temp_session_dir)

        manager.register_artifact(
            path="artifacts/test_data.json",
            artifact_type="data",
            summary="Test data for AI model",
            producer="test",
        )
        manager.register_artifact(
            path="artifacts/report.md",
            artifact_type="document",
            summary="Final report",
            producer="test",
        )

        # 搜索关键词
        results = manager.search_artifacts("test")
        assert len(results) == 1
        assert "test_data.json" in results[0].path

        results = manager.search_artifacts("report")
        assert len(results) == 1

    def test_format_for_prompt(self, temp_session_dir):
        """测试 Prompt 格式化"""
        manager = ArtifactManager(session_dir=temp_session_dir)

        manager.register_artifact(
            path="artifacts/file1.txt", artifact_type="document", summary="File 1", producer="agent"
        )
        manager.register_artifact(
            path="artifacts/file2.py", artifact_type="code", summary="Code 2", producer="agent"
        )

        formatted = manager.format_index_for_prompt(max_items=10)
        assert "Available Artifacts" in formatted
        assert "file1.txt" in formatted
        assert "file2.py" in formatted

    def test_persistence(self, temp_session_dir):
        """测试持久化"""
        # 创建并保存
        manager1 = ArtifactManager(session_dir=temp_session_dir)
        manager1.register_artifact(
            path="artifacts/test.txt", artifact_type="document", summary="Test", producer="test"
        )

        # 重新加载
        manager2 = ArtifactManager(session_dir=temp_session_dir)
        assert len(manager2.index) == 1
        assert "artifacts/test.txt" in manager2.index


class TestMasterContext:
    """测试 MasterContext 类"""

    @pytest.fixture
    def temp_session_dir(self):
        """创建临时 session 目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_initialization(self, temp_session_dir):
        """测试初始化"""
        context = MasterContext(session_dir=temp_session_dir)

        assert context.plan_context is not None
        assert context.decision_path is not None
        assert context.artifact_manager is not None

    def test_update_plan_context(self, temp_session_dir):
        """测试更新计划上下文"""
        context = MasterContext(session_dir=temp_session_dir)

        context.update_plan_context(
            plan_id="P001",
            plan_name="Test Plan",
            plan_description="A test plan",
            current_subtask="Task 1",
            progress="In progress",
        )

        assert context.plan_context.plan_id == "P001"
        assert context.plan_context.plan_name == "Test Plan"
        assert context.plan_context.is_active()

    def test_build_prompt_context(self, temp_session_dir):
        """测试构建 Prompt 上下文"""
        context = MasterContext(session_dir=temp_session_dir)

        # 设置计划
        context.update_plan_context(
            plan_id="P001",
            plan_name="Test Plan",
            plan_description="Description",
        )

        # 添加决策
        context.decision_path.add_decision(
            reasoning="Test",
            action_type="tool",
            action_name="test_tool",
            action_input={},
            action_result="OK",
        )

        # 添加文件
        context.artifact_manager.register_artifact(
            path="artifacts/test.txt",
            artifact_type="document",
            summary="Test file",
            producer="test",
        )

        # 构建 Prompt
        prompt = context.build_prompt_context(
            include_recent_decisions=5,
            include_artifacts_max=10,
            user_message="Please continue",
        )

        assert "PART 1: CURRENT PLAN" in prompt
        assert "PART 2: RECENT DECISION HISTORY" in prompt
        assert "PART 3: AVAILABLE ARTIFACTS" in prompt
        assert "USER MESSAGE" in prompt
        assert "Please continue" in prompt

    def test_context_persistence(self, temp_session_dir):
        """测试上下文持久化"""
        # 创建并保存
        context1 = MasterContext(session_dir=temp_session_dir)
        context1.update_plan_context(
            plan_id="P001",
            plan_name="Test Plan",
        )
        context1.decision_path.add_decision(
            reasoning="Test",
            action_type="tool",
            action_name="tool",
            action_input={},
            action_result="OK",
        )
        context1.save_context()

        # 重新加载
        context2 = MasterContext(session_dir=temp_session_dir)
        assert context2.plan_context.plan_id == "P001"
        assert len(context2.decision_path.decisions) == 1

    def test_get_stats(self, temp_session_dir):
        """测试获取统计信息"""
        context = MasterContext(session_dir=temp_session_dir)

        context.update_plan_context(plan_id="P001")
        context.decision_path.add_decision(
            reasoning="Test",
            action_type="tool",
            action_name="tool",
            action_input={},
            action_result="OK",
        )

        stats = context.get_stats()
        assert stats["has_active_plan"] is True
        assert stats["total_decisions"] == 1
        assert "artifacts" in stats
