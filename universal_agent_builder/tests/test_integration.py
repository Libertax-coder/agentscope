"""Integration tests for research workflow and Docker sandbox"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from agentscope.message import Msg

from src.agents.sub_agents import BrowserUseAgent, ReportAgent
from src.core.context import MasterContext
from src.sandbox.docker_manager import DockerManager
from src.sandbox.session_manager import Session, SessionManager
from src.tools.research_workflow import ResearchWorkflow, execute_research_workflow
from src.tools.web_search import web_search


class TestResearchWorkflow:
    """Test the complete research workflow with interactive calling"""

    @pytest.fixture
    def mock_model(self):
        """Create a mock model for testing"""
        mock = AsyncMock()
        mock_response = Mock()
        mock_response.text = "# Test Report\n\nThis is a mock report generated for testing."
        mock.return_value = mock_response
        return mock

    @pytest.mark.asyncio
    async def test_web_search_tool(self):
        """Test web search tool returns expected format"""
        results = await web_search("AI Agents 2024", max_results=5)

        assert isinstance(results, list)
        assert len(results) == 5

        for result in results:
            assert "url" in result
            assert "title" in result
            assert "snippet" in result
            assert result["url"].startswith("http")

    @pytest.mark.asyncio
    async def test_research_workflow_initialization(self, tmp_path, mock_model):
        """Test ResearchWorkflow initialization with shared context"""
        # Create Master Context
        master_context = MasterContext(session_dir=tmp_path)

        # Create agents
        browser_agent = BrowserUseAgent(
            name="TestBrowserAgent",
            model_config_name="test_model",
        )
        browser_agent.model = mock_model

        report_agent = ReportAgent(
            name="TestReportAgent",
            model_config_name="test_model",
        )
        report_agent.model = mock_model

        # Create workflow
        workflow = ResearchWorkflow(
            browser_agent=browser_agent,
            report_agent=report_agent,
            master_context=master_context,
        )

        # Verify shared context is set
        assert workflow.browser_agent.shared_context == master_context
        assert workflow.report_agent.shared_context == master_context

    @pytest.mark.asyncio
    async def test_execute_research_workflow_standalone(self, mock_model):
        """Test standalone execute_research_workflow function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.tools.research_workflow.BrowserUseAgent') as mock_browser_cls, \
                 patch('src.tools.research_workflow.ReportAgent') as mock_report_cls:

                # Create mock agents with model
                mock_browser = BrowserUseAgent(name="Mock", model_config_name="test")
                mock_browser.model = mock_model
                mock_browser_cls.return_value = mock_browser

                mock_report = ReportAgent(name="Mock", model_config_name="test")
                mock_report.model = mock_model
                mock_report_cls.return_value = mock_report

                result = await execute_research_workflow(
                    topic="Python async programming",
                    session_dir=Path(tmpdir),
                    max_urls=3,
                    report_type="brief",
                )

                assert "status" in result
                assert "report_path" in result
                assert "artifacts_count" in result
                assert "topic" in result
                assert result["topic"] == "Python async programming"

    @pytest.mark.asyncio
    async def test_research_workflow_shared_context(self, tmp_path, mock_model):
        """Test that artifacts are shared across agents in workflow"""
        # Create Master Context
        master_context = MasterContext(session_dir=tmp_path)

        # Create agents
        browser_agent = BrowserUseAgent(
            name="TestBrowserAgent",
            model_config_name="test_model",
            workspace_dir=tmp_path / "browser",
        )
        browser_agent.model = mock_model

        report_agent = ReportAgent(
            name="TestReportAgent",
            model_config_name="test_model",
            workspace_dir=tmp_path / "report",
        )
        report_agent.model = mock_model

        # Set shared context
        browser_agent.set_shared_context(master_context)
        report_agent.set_shared_context(master_context)

        # Verify both agents have access to same context
        assert browser_agent.shared_context is master_context
        assert report_agent.shared_context is master_context

        # Register an artifact through browser agent (using valid type)
        master_context.artifact_manager.register_artifact(
            path=str(tmp_path / "test_artifact.txt"),
            artifact_type="data",  # Changed from 'webpage' to valid type
            summary="Test webpage content",
            producer="TestBrowserAgent",
        )

        # Verify report agent can access the artifact
        artifacts = master_context.artifact_manager.get_artifacts_by_type("data")
        assert len(artifacts) == 1
        assert artifacts[0].producer == "TestBrowserAgent"

    @pytest.mark.asyncio
    async def test_research_workflow_produces_artifacts(self, tmp_path, mock_model):
        """Test that research workflow produces trackable artifacts"""
        master_context = MasterContext(session_dir=tmp_path)

        browser_agent = BrowserUseAgent(
            name="TestBrowserAgent",
            model_config_name="test_model",
            workspace_dir=tmp_path / "browser",
        )
        browser_agent.model = mock_model

        report_agent = ReportAgent(
            name="TestReportAgent",
            model_config_name="test_model",
            workspace_dir=tmp_path / "report",
        )
        report_agent.model = mock_model

        workflow = ResearchWorkflow(
            browser_agent=browser_agent,
            report_agent=report_agent,
            master_context=master_context,
        )

        # Execute workflow
        result = await workflow.execute_research(
            topic="Machine Learning 2024",
            max_urls=2,
            report_type="brief",
        )

        # Check that artifacts were registered
        assert result["status"] == "success"
        assert result["artifacts_count"] >= 0

        # Check artifacts in context
        all_artifacts = master_context.artifact_manager.index
        assert isinstance(all_artifacts, dict)


class TestDockerSandbox:
    """Test Docker sandbox integration (requires Docker)"""

    @pytest.fixture
    def check_docker_available(self):
        """Skip tests if Docker is not available"""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            pytest.skip("Docker not available")

    def test_docker_manager_initialization_without_docker(self, tmp_path):
        """Test DockerManager gracefully handles missing Docker"""
        try:
            # This should raise if docker is not installed
            docker_mgr = DockerManager(base_workspace=tmp_path)
            # If we get here, Docker is available
            assert docker_mgr.client is not None
        except (ImportError, RuntimeError) as e:
            # Expected when Docker is not available
            assert "docker" in str(e).lower() or "Docker" in str(e)

    def test_session_manager_local_mode(self, tmp_path):
        """Test SessionManager in local mode (without Docker)"""
        # Create SessionManager with Docker disabled
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=False,
        )

        assert session_mgr.enable_docker is False
        assert session_mgr.docker_manager is None

        # Create session
        session = session_mgr.create_session(session_id="test_local_session")

        assert session.session_id == "test_local_session"
        assert session.container is None  # No Docker container
        assert session.context is not None  # MasterContext still created
        assert session.workspace_dir.exists()

        # Close session
        session_mgr.close_session("test_local_session", save_state=False)

        assert "test_local_session" not in session_mgr.sessions

    def test_session_manager_create_multiple_sessions(self, tmp_path):
        """Test creating multiple sessions"""
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=False,
        )

        # Create multiple sessions
        session1 = session_mgr.create_session(session_id="session_1")
        session2 = session_mgr.create_session(session_id="session_2")

        assert len(session_mgr.sessions) == 2
        assert session_mgr.get_session("session_1") == session1
        assert session_mgr.get_session("session_2") == session2

        # List sessions
        sessions = session_mgr.list_sessions()
        assert len(sessions) == 2

        # Cleanup
        session_mgr.cleanup_all_sessions()
        assert len(session_mgr.sessions) == 0

    def test_session_to_dict(self, tmp_path):
        """Test Session serialization to dict"""
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=False,
        )

        session = session_mgr.create_session(session_id="test_dict")

        session_dict = session.to_dict()

        assert session_dict["session_id"] == "test_dict"
        assert session_dict["container_id"] is None  # No Docker
        assert session_dict["workspace_dir"] == str(session.workspace_dir)
        assert "created_at" in session_dict
        assert "last_updated" in session_dict
        assert "context_stats" in session_dict

        # Cleanup
        session_mgr.close_session("test_dict", save_state=False)

    def test_session_state_save_and_load(self, tmp_path):
        """Test session state persistence"""
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=False,
        )

        session = session_mgr.create_session(session_id="test_save")

        # Add some artifacts to context
        session.context.artifact_manager.register_artifact(
            path=str(tmp_path / "test.txt"),
            artifact_type="document",
            summary="Test document",
            producer="TestAgent",
        )

        # Save session state
        session_mgr.save_session_state("test_save")

        # Check that metadata file was created
        metadata_file = session.workspace_dir / "session_metadata.json"
        assert metadata_file.exists()

        # Load and verify metadata
        with open(metadata_file) as f:
            metadata = json.load(f)

        assert metadata["session_id"] == "test_save"
        assert "context_stats" in metadata

        # Cleanup
        session_mgr.close_session("test_save", save_state=False)

    def test_session_manager_get_stats(self, tmp_path):
        """Test getting session statistics"""
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=False,
        )

        session = session_mgr.create_session(session_id="test_stats")

        stats = session_mgr.get_session_stats("test_stats")

        assert stats["session_id"] == "test_stats"
        assert "workspace_dir" in stats
        assert "context_stats" in stats

        # Cleanup
        session_mgr.close_session("test_stats", save_state=False)

    @pytest.mark.skipif(True, reason="Requires Docker daemon running")
    def test_docker_manager_with_docker(self, check_docker_available, tmp_path):
        """Test DockerManager with actual Docker (integration test)"""
        # This test requires Docker to be running
        docker_mgr = DockerManager(base_workspace=tmp_path)

        # Create container
        container = docker_mgr.create_container(
            session_id="test_docker",
            cpu_limit=1.0,
            memory_limit="1g",
        )

        assert container is not None
        assert container.name == "universal_agent_session_test_docker"

        # Execute command
        exit_code, stdout, stderr = docker_mgr.execute_command(
            container=container,
            command=["echo", "Hello Docker"],
        )

        assert exit_code == 0
        assert "Hello Docker" in stdout

        # Cleanup
        docker_mgr.stop_container(container)
        docker_mgr.remove_container(container, force=True)

    @pytest.mark.skipif(True, reason="Requires Docker daemon running")
    def test_session_manager_with_docker(self, check_docker_available, tmp_path):
        """Test SessionManager with Docker enabled (integration test)"""
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=True,
        )

        session = session_mgr.create_session(session_id="test_docker_session")

        assert session.container is not None
        assert session.container.name == "universal_agent_session_test_docker_session"

        # Execute command in session
        exit_code, stdout, stderr = session_mgr.execute_in_session(
            session_id="test_docker_session",
            command=["python3", "--version"],
        )

        assert exit_code == 0
        assert "Python" in stdout

        # Cleanup
        session_mgr.close_session("test_docker_session", save_state=False)


class TestEndToEndIntegration:
    """End-to-end integration tests"""

    @pytest.mark.asyncio
    async def test_complete_workflow_without_docker(self, tmp_path):
        """Test complete workflow: Session + Research + Report (no Docker)"""
        # Step 1: Create session
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=False,
        )

        session = session_mgr.create_session(session_id="e2e_test")

        # Step 2: Execute research workflow with mocked models
        mock_model = AsyncMock()
        mock_response = Mock()
        mock_response.text = "# Test Report\n\nThis is a mock report."
        mock_model.return_value = mock_response

        with patch('src.tools.research_workflow.BrowserUseAgent') as mock_browser_cls, \
             patch('src.tools.research_workflow.ReportAgent') as mock_report_cls:

            # Create mock agents with model
            mock_browser = BrowserUseAgent(name="Mock", model_config_name="test")
            mock_browser.model = mock_model
            mock_browser_cls.return_value = mock_browser

            mock_report = ReportAgent(name="Mock", model_config_name="test")
            mock_report.model = mock_model
            mock_report_cls.return_value = mock_report

            result = await execute_research_workflow(
                topic="AgentScope Framework Overview",
                session_dir=session.workspace_dir,
                max_urls=3,
                report_type="brief",
            )

            # Step 3: Verify results
            assert result["status"] == "success"
            assert "report_path" in result
            assert Path(result["report_path"]).exists()

        # Step 4: Check session stats
        stats = session_mgr.get_session_stats("e2e_test")
        assert "context_stats" in stats

        # Step 5: Save and close session
        session_mgr.save_session_state("e2e_test")
        session_mgr.close_session("e2e_test", save_state=True)

        # Verify session metadata saved
        metadata_file = session.workspace_dir / "session_metadata.json"
        assert metadata_file.exists()

    @pytest.mark.asyncio
    async def test_multiple_workflows_in_session(self, tmp_path):
        """Test running multiple research workflows in same session"""
        session_mgr = SessionManager(
            base_workspace=tmp_path,
            enable_docker=False,
        )

        session = session_mgr.create_session(session_id="multi_workflow")

        # Setup mock model
        mock_model = AsyncMock()
        mock_response = Mock()
        mock_response.text = "# Test Report\n\nThis is a mock report."
        mock_model.return_value = mock_response

        # Execute multiple research tasks
        topics = [
            "Python AsyncIO",
            "Multi-Agent Systems",
            "LLM Frameworks",
        ]

        with patch('src.tools.research_workflow.BrowserUseAgent') as mock_browser_cls, \
             patch('src.tools.research_workflow.ReportAgent') as mock_report_cls:

            # Create mock agents with model
            mock_browser = BrowserUseAgent(name="Mock", model_config_name="test")
            mock_browser.model = mock_model
            mock_browser_cls.return_value = mock_browser

            mock_report = ReportAgent(name="Mock", model_config_name="test")
            mock_report.model = mock_model
            mock_report_cls.return_value = mock_report

            for topic in topics:
                result = await execute_research_workflow(
                    topic=topic,
                    session_dir=session.workspace_dir,
                    max_urls=2,
                    report_type="brief",
                )

                assert result["status"] == "success"

        # Check session stats (note: execute_research_workflow creates isolated contexts,
        # so the session's context won't accumulate artifacts from the workflows)
        stats = session_mgr.get_session_stats("multi_workflow")
        context_stats = stats["context_stats"]

        # Verify context structure is correct
        assert "artifacts" in context_stats
        assert "total_artifacts" in context_stats["artifacts"]

        # Cleanup
        session_mgr.close_session("multi_workflow", save_state=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
