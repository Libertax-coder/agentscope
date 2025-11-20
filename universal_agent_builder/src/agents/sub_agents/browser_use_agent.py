"""Browser Use Agent - 浏览器自动化智能体

负责网页浏览、信息提取、数据收集
"""

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

from agentscope.agent import AgentBase
from agentscope.message import Msg


class BrowserUseAgent(AgentBase):
    """浏览器自动化智能体

    职责：
    - 浏览网页并提取信息
    - 提取结构化数据
    - 保存网页内容
    - 与 Web Search 配合使用

    支持独立调用和交互式调用两种模式
    """

    def __init__(
        self,
        name: str = "BrowserUseAgent",
        model_config_name: str | None = None,
        workspace_dir: str | Path | None = None,
        timeout: int = 30,
        **kwargs: Any,
    ):
        """初始化 Browser Use Agent

        Args:
            name: Agent 名称
            model_config_name: 模型配置名称
            workspace_dir: 工作目录
            timeout: 请求超时时间（秒）
            **kwargs: 其他参数
        """
        super().__init__()

        self.name = name
        self.model_config_name = model_config_name
        self.timeout = timeout

        # 检查依赖
        if requests is None or BeautifulSoup is None:
            raise ImportError(
                "BrowserUseAgent requires 'requests' and 'beautifulsoup4'. "
                "Install with: pip install requests beautifulsoup4"
            )

        # 工作目录
        if workspace_dir is None:
            workspace_dir = Path.cwd() / "workspace" / "browser_agent"
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Browser 工作目录
        self.browser_dir = self.workspace_dir / "browser"
        self.browser_dir.mkdir(parents=True, exist_ok=True)

        # 共享 Context（用于交互式调用）
        self.shared_context = None

        # 产生的文件列表
        self.produced_artifacts: list[dict[str, Any]] = []

        # Session（保持 cookies）
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    async def reply(self, x: Msg) -> Msg:
        """处理用户消息

        Args:
            x: 用户消息

        Returns:
            Msg: 响应消息
        """
        user_input = x.content

        # 解析用户输入
        task_info = self._parse_user_input(user_input)

        task_type = task_info.get("task_type", "unknown")
        url = task_info.get("url", "")

        # 根据任务类型执行
        if task_type == "browse_and_extract":
            result = await self.browse_and_extract(
                url=url,
                extraction_task=task_info.get("extraction_task", "Extract main content"),
            )
        elif task_type == "extract_structured_data":
            result = await self.extract_structured_data(
                url=url,
                data_schema=task_info.get("data_schema", {}),
            )
        elif task_type == "save_page":
            result = await self.save_page_content(
                url=url,
                format_type=task_info.get("format", "text"),
            )
        elif task_type == "multi_page_research":
            urls = task_info.get("urls", [url] if url else [])
            result = await self.multi_page_research(
                urls=urls,
                research_topic=task_info.get("research_topic", ""),
            )
        else:
            # 使用 LLM 理解任务
            result = await self._handle_general_task(user_input)

        return Msg(
            name=self.name,
            content=result,
            role="assistant",
        )

    def _parse_user_input(self, user_input: str) -> dict[str, Any]:
        """解析用户输入

        Args:
            user_input: 用户输入字符串

        Returns:
            dict: 解析后的任务信息
        """
        # 尝试解析 JSON
        if isinstance(user_input, dict):
            return user_input

        try:
            task_info = json.loads(user_input)
            return task_info
        except json.JSONDecodeError:
            pass

        # 提取 URL
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, user_input)

        # 关键词匹配
        if "extract" in user_input.lower() and urls:
            return {
                "task_type": "browse_and_extract",
                "url": urls[0],
                "extraction_task": user_input,
            }
        elif "structured" in user_input.lower() and urls:
            return {
                "task_type": "extract_structured_data",
                "url": urls[0],
            }
        elif "save" in user_input.lower() and urls:
            return {
                "task_type": "save_page",
                "url": urls[0],
            }
        elif len(urls) > 1:
            return {
                "task_type": "multi_page_research",
                "urls": urls,
                "research_topic": user_input,
            }
        elif urls:
            return {
                "task_type": "browse_and_extract",
                "url": urls[0],
                "extraction_task": user_input,
            }
        else:
            return {"task_type": "general", "description": user_input}

    async def browse_and_extract(
        self,
        url: str,
        extraction_task: str,
    ) -> str:
        """浏览 URL 并提取信息

        Args:
            url: 目标 URL
            extraction_task: 提取任务描述

        Returns:
            str: 提取结果
        """
        try:
            # 获取网页内容
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding

            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()

            # 提取文本
            text_content = soup.get_text(separator='\n', strip=True)

            # 保存原始内容
            saved_file = await self.save_page_content(url, "text")

            # 使用 LLM 进行智能提取
            extraction_result = await self._extract_with_llm(
                text_content, extraction_task, url
            )

            # 保存提取结果
            data_file = self.browser_dir / "data" / f"{self._sanitize_filename(url)}_extracted.json"
            data_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "url": url,
                "extraction_task": extraction_task,
                "extracted_content": extraction_result,
                "timestamp": self._get_timestamp(),
            }

            data_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

            self._register_artifact(
                path=str(data_file),
                artifact_type="data",
                summary=f"Extracted data from {url}",
            )

            return f"Extraction completed.\n\n{extraction_result}\n\nData saved to: {data_file}"

        except requests.RequestException as e:
            return f"Error browsing URL {url}: {str(e)}"
        except Exception as e:
            return f"Error extracting content: {str(e)}"

    async def _extract_with_llm(
        self,
        text_content: str,
        extraction_task: str,
        url: str,
    ) -> str:
        """使用 LLM 进行智能提取

        Args:
            text_content: 网页文本内容
            extraction_task: 提取任务
            url: URL

        Returns:
            str: 提取结果
        """
        # 限制文本长度
        max_length = 4000
        if len(text_content) > max_length:
            text_content = text_content[:max_length] + "\n\n[Content truncated...]"

        prompt = f"""Extract information from the following web page content.

URL: {url}

Task: {extraction_task}

Web Page Content:
{text_content}

Please extract the relevant information based on the task and provide a clear, structured response.
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        return response.text

    async def extract_structured_data(
        self,
        url: str,
        data_schema: dict[str, Any] | None = None,
    ) -> str:
        """提取结构化数据

        Args:
            url: 目标 URL
            data_schema: 数据模式（可选）

        Returns:
            str: 提取结果
        """
        try:
            # 获取网页内容
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # 使用 LLM 提取结构化数据
            text_content = soup.get_text(separator='\n', strip=True)[:4000]

            prompt = f"""Extract structured data from the web page.

URL: {url}

"""
            if data_schema:
                prompt += f"""Expected data schema:
{json.dumps(data_schema, indent=2)}

"""

            prompt += f"""Web Page Content:
{text_content}

Please extract data in JSON format matching the schema (if provided) or in a logical structure.
"""

            response_msg = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

            # 尝试解析 JSON
            extracted_data = self._extract_json(response_msg.text)

            # 保存数据
            data_file = self.browser_dir / "data" / f"{self._sanitize_filename(url)}_structured.json"
            data_file.parent.mkdir(parents=True, exist_ok=True)

            data_file.write_text(
                json.dumps(extracted_data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            self._register_artifact(
                path=str(data_file),
                artifact_type="data",
                summary=f"Structured data from {url}",
            )

            return f"Structured data extracted and saved to: {data_file}\n\nData:\n{json.dumps(extracted_data, indent=2)}"

        except Exception as e:
            return f"Error extracting structured data: {str(e)}"

    async def save_page_content(
        self,
        url: str,
        format_type: str = "text",
    ) -> str:
        """保存网页内容

        Args:
            url: 目标 URL
            format_type: 格式类型（text/html）

        Returns:
            str: 保存的文件路径
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # 确定文件路径
            filename = self._sanitize_filename(url)
            if format_type == "html":
                file_path = self.browser_dir / "downloads" / f"{filename}.html"
                content = response.text
            else:
                soup = BeautifulSoup(response.text, 'html.parser')
                for script in soup(["script", "style"]):
                    script.decompose()
                content = soup.get_text(separator='\n', strip=True)
                file_path = self.browser_dir / "downloads" / f"{filename}.txt"

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

            self._register_artifact(
                path=str(file_path),
                artifact_type="document",
                summary=f"Page content from {url}",
            )

            return str(file_path)

        except Exception as e:
            raise Exception(f"Error saving page content: {str(e)}")

    async def multi_page_research(
        self,
        urls: list[str],
        research_topic: str = "",
    ) -> str:
        """多页面研究任务

        Args:
            urls: URL 列表
            research_topic: 研究主题

        Returns:
            str: 研究结果
        """
        results = []

        for url in urls[:5]:  # 限制最多 5 个页面
            try:
                result = await self.browse_and_extract(
                    url=url,
                    extraction_task=f"Extract information related to: {research_topic}",
                )
                results.append(f"### {url}\n\n{result}\n")
            except Exception as e:
                results.append(f"### {url}\n\nError: {str(e)}\n")

        # 汇总结果
        summary_file = self.browser_dir / "data" / "research_summary.md"
        summary_file.parent.mkdir(parents=True, exist_ok=True)

        summary_content = f"# Research: {research_topic}\n\n" + "\n".join(results)
        summary_file.write_text(summary_content, encoding="utf-8")

        self._register_artifact(
            path=str(summary_file),
            artifact_type="document",
            summary=f"Research summary: {research_topic}",
        )

        return f"Multi-page research completed.\n\nSummary saved to: {summary_file}\n\n{summary_content[:1000]}..."

    async def _handle_general_task(self, user_input: str) -> str:
        """处理通用任务（使用 LLM）

        Args:
            user_input: 用户输入

        Returns:
            str: 处理结果
        """
        prompt = f"""You are a browser automation agent. The user has requested:

{user_input}

Analyze the request and provide guidance on what browser actions would be needed.
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        return response.text

    def _sanitize_filename(self, url: str) -> str:
        """清理 URL 生成合法的文件名

        Args:
            url: URL

        Returns:
            str: 文件名
        """
        parsed = urlparse(url)
        filename = f"{parsed.netloc}_{parsed.path}".replace("/", "_").replace(":", "_")
        # 移除非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 限制长度
        return filename[:100]

    def _extract_json(self, text: str) -> dict | list:
        """从文本中提取 JSON

        Args:
            text: 文本

        Returns:
            dict | list: JSON 数据
        """
        # 尝试提取 JSON 代码块
        json_match = re.search(r'```json\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取大括号或方括号内容
        json_match = re.search(r'[\{\[].*[\}\]]', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # 返回原始文本作为数据
        return {"content": text}

    def _get_timestamp(self) -> str:
        """获取时间戳

        Returns:
            str: ISO 格式时间戳
        """
        from datetime import datetime
        return datetime.now().isoformat()

    def _register_artifact(
        self,
        path: str,
        artifact_type: str,
        summary: str,
    ):
        """注册产生的文件

        Args:
            path: 文件路径
            artifact_type: 文件类型
            summary: 文件摘要
        """
        self.produced_artifacts.append({
            "path": path,
            "type": artifact_type,
            "summary": summary,
            "producer": self.name,
        })

    def get_produced_artifacts(self) -> list[dict[str, Any]]:
        """获取产生的文件列表

        Returns:
            list: 文件列表
        """
        return self.produced_artifacts

    def set_shared_context(self, context: Any):
        """设置共享 Context（用于交互式调用）

        Args:
            context: MasterContext 对象
        """
        self.shared_context = context
