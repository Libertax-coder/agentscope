"""Tests for Sub-Agents (Code, Browser Use, Report)"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

import pytest

from src.agents.sub_agents.code_agent import CodeAgent
from src.agents.sub_agents.browser_use_agent import BrowserUseAgent
from src.agents.sub_agents.report_agent import ReportAgent


class TestCodeAgent:
    """测试 Code Agent"""

    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_code_agent_initialization(self, temp_workspace):
        """测试 Code Agent 初始化"""
        agent = CodeAgent(
            name="TestCodeAgent",
            workspace_dir=temp_workspace,
        )

        assert agent.name == "TestCodeAgent"
        assert agent.workspace_dir == temp_workspace
        assert agent.workspace_dir.exists()

    def test_parse_user_input_json(self, temp_workspace):
        """测试解析 JSON 输入"""
        agent = CodeAgent(workspace_dir=temp_workspace)

        input_dict = {
            "task_type": "generate_chart",
            "data": {"A": 10, "B": 20},
            "chart_type": "bar",
        }

        task_info = agent._parse_user_input(input_dict)

        assert task_info["task_type"] == "generate_chart"
        assert task_info["data"] == {"A": 10, "B": 20}

    def test_parse_user_input_keywords(self, temp_workspace):
        """测试关键词匹配"""
        agent = CodeAgent(workspace_dir=temp_workspace)

        # 执行 Python 代码
        task_info = agent._parse_user_input("execute this python code")
        assert task_info["task_type"] == "execute_python"

        # 生成图表
        task_info = agent._parse_user_input("plot a chart for me")
        assert task_info["task_type"] == "generate_chart"

        # 生成代码
        task_info = agent._parse_user_input("generate code for sorting")
        assert task_info["task_type"] == "generate_code"

    @pytest.mark.asyncio
    async def test_write_code_file(self, temp_workspace):
        """测试写入代码文件"""
        agent = CodeAgent(workspace_dir=temp_workspace)

        code = "print('Hello, World!')"
        result = await agent.write_code_file(
            filename="hello.py",
            code=code,
            language="python",
        )

        assert "successfully" in result.lower()
        assert (temp_workspace / "code" / "hello.py").exists()

        # 检查文件内容
        saved_code = (temp_workspace / "code" / "hello.py").read_text()
        assert saved_code == code

        # 检查 artifacts
        assert len(agent.produced_artifacts) == 1
        assert agent.produced_artifacts[0]["type"] == "code"

    def test_get_file_extension(self, temp_workspace):
        """测试文件扩展名获取"""
        agent = CodeAgent(workspace_dir=temp_workspace)

        assert agent._get_file_extension("python") == "py"
        assert agent._get_file_extension("javascript") == "js"
        assert agent._get_file_extension("java") == "java"
        assert agent._get_file_extension("unknown") == "txt"

    def test_extract_code(self, temp_workspace):
        """测试代码提取"""
        agent = CodeAgent(workspace_dir=temp_workspace)

        # 提取 Python 代码块
        text = """
Here is the code:
```python
print('test')
```
"""
        code = agent._extract_code(text, "python")
        assert code == "print('test')"

        # 提取通用代码块
        text = """
```
console.log('test')
```
"""
        code = agent._extract_code(text, "javascript")
        assert code == "console.log('test')"

    def test_generate_plot_code(self, temp_workspace):
        """测试绘图代码生成"""
        agent = CodeAgent(workspace_dir=temp_workspace)

        # 字典数据
        code = agent._generate_plot_code(
            data={"A": 10, "B": 20},
            chart_type="bar",
            title="Test Chart",
            xlabel="X",
            ylabel="Y",
        )

        assert "import matplotlib" in code
        assert "plt.bar" in code
        assert "Test Chart" in code

    def test_set_shared_context(self, temp_workspace):
        """测试设置共享 Context"""
        agent = CodeAgent(workspace_dir=temp_workspace)

        mock_context = Mock()
        agent.set_shared_context(mock_context)

        assert agent.shared_context is mock_context


class TestBrowserUseAgent:
    """测试 Browser Use Agent"""

    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_browser_agent_initialization(self, temp_workspace):
        """测试 Browser Use Agent 初始化"""
        with patch('src.agents.sub_agents.browser_use_agent.requests'), \
             patch('src.agents.sub_agents.browser_use_agent.BeautifulSoup'):

            agent = BrowserUseAgent(
                name="TestBrowserAgent",
                workspace_dir=temp_workspace,
                timeout=15,
            )

            assert agent.name == "TestBrowserAgent"
            assert agent.workspace_dir == temp_workspace
            assert agent.timeout == 15

    def test_parse_user_input_with_url(self, temp_workspace):
        """测试解析包含 URL 的输入"""
        with patch('src.agents.sub_agents.browser_use_agent.requests'), \
             patch('src.agents.sub_agents.browser_use_agent.BeautifulSoup'):

            agent = BrowserUseAgent(workspace_dir=temp_workspace)

            # 单个 URL - 提取任务
            task_info = agent._parse_user_input(
                "extract information from https://example.com"
            )
            assert task_info["task_type"] == "browse_and_extract"
            assert task_info["url"] == "https://example.com"

            # 多个 URL - 多页面研究
            task_info = agent._parse_user_input(
                "research https://example.com and https://test.com"
            )
            assert task_info["task_type"] == "multi_page_research"
            assert len(task_info["urls"]) == 2

    def test_sanitize_filename(self, temp_workspace):
        """测试文件名清理"""
        with patch('src.agents.sub_agents.browser_use_agent.requests'), \
             patch('src.agents.sub_agents.browser_use_agent.BeautifulSoup'):

            agent = BrowserUseAgent(workspace_dir=temp_workspace)

            filename = agent._sanitize_filename("https://example.com/path/to/page?query=test")

            # 应该移除非法字符
            assert "<" not in filename
            assert ">" not in filename
            assert "?" not in filename

            # 应该包含域名
            assert "example.com" in filename

    def test_extract_json(self, temp_workspace):
        """测试 JSON 提取"""
        with patch('src.agents.sub_agents.browser_use_agent.requests'), \
             patch('src.agents.sub_agents.browser_use_agent.BeautifulSoup'):

            agent = BrowserUseAgent(workspace_dir=temp_workspace)

            # JSON 代码块
            text = """
Here is the data:
```json
{"name": "test", "value": 123}
```
"""
            data = agent._extract_json(text)
            assert data == {"name": "test", "value": 123}

            # 大括号内容
            text = '{"key": "value"}'
            data = agent._extract_json(text)
            assert data == {"key": "value"}

            # 无效 JSON - 返回包装的内容
            text = "not a json"
            data = agent._extract_json(text)
            assert "content" in data


class TestReportAgent:
    """测试 Report Agent"""

    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_report_agent_initialization(self, temp_workspace):
        """测试 Report Agent 初始化"""
        agent = ReportAgent(
            name="TestReportAgent",
            workspace_dir=temp_workspace,
        )

        assert agent.name == "TestReportAgent"
        assert agent.workspace_dir == temp_workspace
        assert agent.documents_dir.exists()

    def test_parse_user_input(self, temp_workspace):
        """测试解析用户输入"""
        agent = ReportAgent(workspace_dir=temp_workspace)

        # 研究报告
        task_info = agent._parse_user_input("generate a research report on AI agents")
        assert task_info["task_type"] == "generate_research_report"

        # 技术文档
        task_info = agent._parse_user_input("create technical doc for the API")
        assert task_info["task_type"] == "create_technical_doc"

        # 格式化
        task_info = agent._parse_user_input("format this document")
        assert task_info["task_type"] == "format_document"

        # 总结
        task_info = agent._parse_user_input("summarize the following content")
        assert task_info["task_type"] == "summarize"

    def test_sanitize_filename(self, temp_workspace):
        """测试文件名清理"""
        agent = ReportAgent(workspace_dir=temp_workspace)

        filename = agent._sanitize_filename("AI Agents: The Future?")

        # 应该移除非法字符
        assert ":" not in filename
        assert "?" not in filename

        # 应该替换空格
        assert " " not in filename
        assert "_" in filename

    @pytest.mark.asyncio
    async def test_summarize_content(self, temp_workspace):
        """测试内容总结"""
        agent = ReportAgent(workspace_dir=temp_workspace)

        # Mock LLM
        mock_response = Mock()
        mock_response.text = "This is a brief summary."
        agent.model = AsyncMock(return_value=mock_response)

        result = await agent.summarize_content(
            content="Long content here...",
            summary_type="brief",
        )

        assert "summary" in result.lower()
        agent.model.assert_called_once()

    def test_extract_context_info(self, temp_workspace):
        """测试从 shared_context 提取信息"""
        agent = ReportAgent(workspace_dir=temp_workspace)

        # 无 shared_context
        info = agent._extract_context_info()
        assert info == ""

        # 有 shared_context
        from src.core.context import MasterContext

        mock_context = MasterContext(session_dir=temp_workspace)
        agent.set_shared_context(mock_context)

        info = agent._extract_context_info()
        # 应该包含一些信息（即使是空的 context 也有默认结构）
        assert isinstance(info, str)

    def test_extract_code_artifacts(self, temp_workspace):
        """测试提取代码文件"""
        agent = ReportAgent(workspace_dir=temp_workspace)

        # 无 shared_context
        artifacts = agent._extract_code_artifacts()
        assert artifacts == []

        # 有 shared_context
        from src.core.context import MasterContext

        mock_context = MasterContext(session_dir=temp_workspace)

        # 添加一些代码 artifacts
        mock_context.artifact_manager.register_artifact(
            path="test.py",
            artifact_type="code",
            summary="Test code",
            producer="test",
        )

        agent.set_shared_context(mock_context)

        artifacts = agent._extract_code_artifacts()
        assert len(artifacts) == 1
        assert artifacts[0] == "test.py"

    def test_get_produced_artifacts(self, temp_workspace):
        """测试获取产生的文件"""
        agent = ReportAgent(workspace_dir=temp_workspace)

        # 初始为空
        assert len(agent.get_produced_artifacts()) == 0

        # 注册一个文件
        agent._register_artifact(
            path="/path/to/report.md",
            artifact_type="document",
            summary="Test report",
        )

        artifacts = agent.get_produced_artifacts()
        assert len(artifacts) == 1
        assert artifacts[0]["type"] == "document"
