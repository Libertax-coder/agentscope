"""Research Workflow - 完整的信息检索工作流

演示 Web Search + Browser Use Agent + Report Agent 的交互式调用
"""

from typing import Any
from pathlib import Path

from ..agents.sub_agents.browser_use_agent import BrowserUseAgent
from ..agents.sub_agents.report_agent import ReportAgent
from ..core.context import MasterContext
from .web_search import web_search


class ResearchWorkflow:
    """研究工作流

    完整的信息检索流程：
    1. Web Search 获取相关 URL
    2. Browser Use Agent 详细浏览（交互式调用，共享 Context）
    3. Report Agent 整合报告（交互式调用，访问所有浏览结果）
    """

    def __init__(
        self,
        browser_agent: BrowserUseAgent,
        report_agent: ReportAgent,
        master_context: MasterContext,
    ):
        """初始化研究工作流

        Args:
            browser_agent: Browser Use Agent 实例
            report_agent: Report Agent 实例
            master_context: Master Context 实例（用于共享）
        """
        self.browser_agent = browser_agent
        self.report_agent = report_agent
        self.master_context = master_context

        # 设置共享 Context
        self.browser_agent.set_shared_context(master_context)
        self.report_agent.set_shared_context(master_context)

    async def execute_research(
        self,
        topic: str,
        max_urls: int = 5,
        report_type: str = "detailed",
    ) -> dict[str, Any]:
        """执行完整的研究工作流

        Args:
            topic: 研究主题
            max_urls: 最大浏览的 URL 数量
            report_type: 报告类型（brief/detailed/comprehensive）

        Returns:
            dict: 研究结果，包含：
                - search_results: 搜索结果
                - browsed_pages: 浏览的页面数
                - report_path: 生成的报告路径
                - artifacts: 产生的所有文件
        """
        results = {
            "topic": topic,
            "search_results": [],
            "browsed_pages": 0,
            "report_path": None,
            "artifacts": [],
        }

        # Step 1: Web Search 获取相关 URL
        print(f"[ResearchWorkflow] Step 1: Searching for '{topic}'...")
        search_results = await web_search(topic, max_results=max_urls)
        results["search_results"] = search_results

        print(f"[ResearchWorkflow] Found {len(search_results)} search results.")

        # Step 2: Browser Use Agent 详细浏览（交互式调用）
        print(f"[ResearchWorkflow] Step 2: Browsing top {max_urls} pages...")

        from agentscope.message import Msg

        for idx, result in enumerate(search_results[:max_urls], 1):
            url = result["url"]
            print(f"[ResearchWorkflow]   [{idx}/{max_urls}] Browsing {url}...")

            try:
                # 构建浏览任务（JSON 格式）
                task_input = {
                    "task_type": "browse_and_extract",
                    "url": url,
                    "extraction_task": f"Extract information related to: {topic}",
                }

                # 调用 Browser Use Agent（交互式调用）
                input_msg = Msg(
                    name="ResearchWorkflow",
                    content=str(task_input),
                    role="user",
                    metadata={"context": self.master_context},
                )

                response = await self.browser_agent.reply(input_msg)

                print(f"[ResearchWorkflow]   ✓ Browsed successfully")
                results["browsed_pages"] += 1

                # Browser Use Agent 产生的 artifacts 会自动注册到 master_context

            except Exception as e:
                print(f"[ResearchWorkflow]   ✗ Error browsing {url}: {str(e)}")

        # Step 3: Report Agent 整合报告（交互式调用）
        print(f"[ResearchWorkflow] Step 3: Generating {report_type} report...")

        task_input = {
            "task_type": "generate_research_report",
            "topic": topic,
            "report_type": report_type,
        }

        input_msg = Msg(
            name="ResearchWorkflow",
            content=str(task_input),
            role="user",
            metadata={"context": self.master_context},
        )

        response = await self.report_agent.reply(input_msg)

        # 提取报告路径
        if "saved to:" in response.content:
            import re

            match = re.search(r"saved to:\s*(.+?)(?:\n|$)", response.content)
            if match:
                results["report_path"] = match.group(1).strip()

        print(f"[ResearchWorkflow] ✓ Report generated")

        # 收集所有 artifacts
        results["artifacts"] = (
            self.browser_agent.get_produced_artifacts()
            + self.report_agent.get_produced_artifacts()
        )
        results["artifacts_count"] = len(results["artifacts"])
        results["status"] = "success"  # 标记为成功完成

        print(f"[ResearchWorkflow] Research completed!")
        print(f"  - Browsed pages: {results['browsed_pages']}")
        print(f"  - Total artifacts: {len(results['artifacts'])}")
        print(f"  - Report: {results['report_path']}")

        return results


# 便捷函数：直接执行研究工作流
async def execute_research_workflow(
    topic: str,
    session_dir: str | Path,
    max_urls: int = 5,
    report_type: str = "detailed",
) -> dict[str, Any]:
    """执行研究工作流的便捷函数

    Args:
        topic: 研究主题
        session_dir: Session 目录
        max_urls: 最大浏览 URL 数
        report_type: 报告类型

    Returns:
        dict: 研究结果
    """
    # 创建必要的组件
    master_context = MasterContext(session_dir=session_dir)

    browser_agent = BrowserUseAgent(
        workspace_dir=Path(session_dir) / "browser_workspace"
    )

    report_agent = ReportAgent(
        workspace_dir=Path(session_dir) / "report_workspace"
    )

    # 创建工作流
    workflow = ResearchWorkflow(
        browser_agent=browser_agent,
        report_agent=report_agent,
        master_context=master_context,
    )

    # 执行研究
    return await workflow.execute_research(
        topic=topic,
        max_urls=max_urls,
        report_type=report_type,
    )
