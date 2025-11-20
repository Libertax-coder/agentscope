"""Report Agent - 报告生成智能体

负责生成各类研究报告和技术文档
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from agentscope.agent import AgentBase
from agentscope.message import Msg


class ReportAgent(AgentBase):
    """报告生成智能体

    职责：
    - 生成研究报告（Markdown/PDF）
    - 生成技术文档
    - 格式化文档
    - 整合多源信息

    支持独立调用和交互式调用两种模式
    """

    def __init__(
        self,
        name: str = "ReportAgent",
        model_config_name: str | None = None,
        workspace_dir: str | Path | None = None,
        **kwargs: Any,
    ):
        """初始化 Report Agent

        Args:
            name: Agent 名称
            model_config_name: 模型配置名称
            workspace_dir: 工作目录
            **kwargs: 其他参数
        """
        super().__init__()

        self.name = name
        self.model_config_name = model_config_name

        # 工作目录
        if workspace_dir is None:
            workspace_dir = Path.cwd() / "workspace" / "report_agent"
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # 文档目录
        self.documents_dir = self.workspace_dir / "documents"
        self.documents_dir.mkdir(parents=True, exist_ok=True)

        # 共享 Context（用于交互式调用）
        self.shared_context = None

        # 产生的文件列表
        self.produced_artifacts: list[dict[str, Any]] = []

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

        # 根据任务类型执行
        if task_type == "generate_research_report":
            result = await self.generate_research_report(
                topic=task_info.get("topic", "Research Topic"),
                sources=task_info.get("sources", []),
            )
        elif task_type == "create_technical_doc":
            result = await self.create_technical_doc(
                title=task_info.get("title", "Technical Documentation"),
                content_outline=task_info.get("outline", {}),
            )
        elif task_type == "format_document":
            result = await self.format_document(
                raw_content=task_info.get("content", ""),
                format_style=task_info.get("style", "standard"),
            )
        elif task_type == "summarize":
            result = await self.summarize_content(
                content=task_info.get("content", ""),
                summary_type=task_info.get("summary_type", "brief"),
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

        # 关键词匹配
        if "research" in user_input.lower() and "report" in user_input.lower():
            return {"task_type": "generate_research_report", "topic": user_input}
        elif "technical" in user_input.lower() and "doc" in user_input.lower():
            return {"task_type": "create_technical_doc", "title": user_input}
        elif "format" in user_input.lower():
            return {"task_type": "format_document", "content": user_input}
        elif "summarize" in user_input.lower() or "summary" in user_input.lower():
            return {"task_type": "summarize", "content": user_input}
        else:
            return {"task_type": "generate_research_report", "topic": user_input}

    async def generate_research_report(
        self,
        topic: str,
        sources: list[str] | None = None,
        report_type: Literal["brief", "detailed", "comprehensive"] = "detailed",
    ) -> str:
        """生成深度研究报告

        Args:
            topic: 研究主题
            sources: 信息来源列表（如果使用交互式调用，会从 shared_context 读取）
            report_type: 报告类型

        Returns:
            str: 报告路径和摘要
        """
        # 如果使用交互式调用，从 shared_context 获取信息
        context_info = ""
        if self.shared_context:
            context_info = self._extract_context_info()

        # 如果提供了 sources，添加到 context
        if sources:
            context_info += "\n\n## Provided Sources:\n\n"
            for idx, source in enumerate(sources, 1):
                context_info += f"{idx}. {source}\n"

        # 使用 LLM 生成报告
        report_content = await self._generate_report_with_llm(
            topic, context_info, report_type
        )

        # 保存报告
        filename = self._sanitize_filename(f"{topic}_report.md")
        report_file = self.documents_dir / filename

        report_file.write_text(report_content, encoding="utf-8")

        self._register_artifact(
            path=str(report_file),
            artifact_type="document",
            summary=f"Research report: {topic}",
        )

        return f"Research report generated and saved to: {report_file}\n\n{report_content[:500]}..."

    async def _generate_report_with_llm(
        self,
        topic: str,
        context_info: str,
        report_type: str,
    ) -> str:
        """使用 LLM 生成报告

        Args:
            topic: 主题
            context_info: 上下文信息
            report_type: 报告类型

        Returns:
            str: 报告内容（Markdown 格式）
        """
        depth_instructions = {
            "brief": "Provide a concise summary (1-2 pages).",
            "detailed": "Provide a detailed analysis (3-5 pages).",
            "comprehensive": "Provide a comprehensive deep-dive report (5-10 pages).",
        }

        prompt = f"""Generate a {report_type} research report on the following topic.

Topic: {topic}

{depth_instructions.get(report_type, '')}

"""

        if context_info:
            prompt += f"""Available Information:
{context_info[:3000]}

"""

        prompt += """Please structure the report in Markdown format with the following sections:

# [Report Title]

## Executive Summary
Brief overview of the topic and key findings.

## Introduction
Background and context.

## Main Analysis
Detailed analysis and findings (with subsections as needed).

## Conclusion
Summary of insights and implications.

## References
(If applicable)

Please make the report informative, well-structured, and professional.
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        # 添加元数据头部
        metadata = f"""---
title: {topic}
date: {datetime.now().strftime('%Y-%m-%d')}
type: {report_type}
generated_by: {self.name}
---

"""

        return metadata + response.text

    async def create_technical_doc(
        self,
        title: str,
        content_outline: dict[str, Any] | None = None,
        code_artifacts: list[str] | None = None,
    ) -> str:
        """创建技术文档

        Args:
            title: 文档标题
            content_outline: 内容大纲
            code_artifacts: 代码文件列表

        Returns:
            str: 文档路径
        """
        # 从 shared_context 获取代码文件（如果交互式调用）
        if self.shared_context and not code_artifacts:
            code_artifacts = self._extract_code_artifacts()

        # 使用 LLM 生成技术文档
        doc_content = await self._generate_technical_doc_with_llm(
            title, content_outline, code_artifacts
        )

        # 保存文档
        filename = self._sanitize_filename(f"{title}_doc.md")
        doc_file = self.documents_dir / filename

        doc_file.write_text(doc_content, encoding="utf-8")

        self._register_artifact(
            path=str(doc_file),
            artifact_type="document",
            summary=f"Technical documentation: {title}",
        )

        return f"Technical documentation generated and saved to: {doc_file}"

    async def _generate_technical_doc_with_llm(
        self,
        title: str,
        content_outline: dict | None,
        code_artifacts: list | None,
    ) -> str:
        """使用 LLM 生成技术文档

        Args:
            title: 标题
            content_outline: 大纲
            code_artifacts: 代码文件

        Returns:
            str: 文档内容
        """
        prompt = f"""Generate technical documentation for: {title}

"""

        if content_outline:
            prompt += f"""Content Outline:
{json.dumps(content_outline, indent=2)}

"""

        if code_artifacts:
            prompt += f"""Code Artifacts:
{chr(10).join(f'- {artifact}' for artifact in code_artifacts[:10])}

"""

        prompt += """Please create comprehensive technical documentation with:

# [Title]

## Overview
Brief introduction and purpose.

## Architecture
System architecture and design.

## API Reference
(If applicable) API endpoints, parameters, responses.

## Usage
How to use the system/code.

## Examples
Practical examples.

## Troubleshooting
Common issues and solutions.

Format in clear Markdown with code examples where appropriate.
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        metadata = f"""---
title: {title}
date: {datetime.now().strftime('%Y-%m-%d')}
type: technical_documentation
generated_by: {self.name}
---

"""

        return metadata + response.text

    async def format_document(
        self,
        raw_content: str,
        format_style: Literal["standard", "academic", "technical", "executive"] = "standard",
    ) -> str:
        """格式化文档

        Args:
            raw_content: 原始内容
            format_style: 格式风格

        Returns:
            str: 格式化后的文档路径
        """
        prompt = f"""Format the following content in {format_style} style with proper Markdown structure.

Content:
{raw_content}

Please provide:
- Proper headings and hierarchy
- Clear structure
- Professional formatting
- Table of contents if needed
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        # 保存格式化文档
        filename = f"formatted_document_{format_style}.md"
        doc_file = self.documents_dir / filename

        doc_file.write_text(response.text, encoding="utf-8")

        self._register_artifact(
            path=str(doc_file),
            artifact_type="document",
            summary=f"Formatted document ({format_style} style)",
        )

        return f"Document formatted and saved to: {doc_file}"

    async def summarize_content(
        self,
        content: str,
        summary_type: Literal["brief", "detailed", "bullet_points"] = "brief",
    ) -> str:
        """总结内容

        Args:
            content: 要总结的内容
            summary_type: 总结类型

        Returns:
            str: 总结结果
        """
        instructions = {
            "brief": "Provide a brief 2-3 sentence summary.",
            "detailed": "Provide a detailed paragraph summary.",
            "bullet_points": "Provide key points in bullet-point format.",
        }

        prompt = f"""Summarize the following content.

{instructions.get(summary_type, '')}

Content:
{content[:4000]}

Please provide a clear and concise summary.
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        return response.text

    def _extract_context_info(self) -> str:
        """从 shared_context 提取信息

        Returns:
            str: 格式化的上下文信息
        """
        if not self.shared_context:
            return ""

        info_parts = []

        # 提取 Artifacts
        if hasattr(self.shared_context, 'artifact_manager'):
            artifacts = self.shared_context.artifact_manager.index
            if artifacts:
                info_parts.append("## Available Data and Documents:\n")
                for path, metadata in list(artifacts.items())[:20]:
                    info_parts.append(f"- {metadata.summary} ({path})")

        # 提取最近的决策（了解已完成的工作）
        if hasattr(self.shared_context, 'decision_path'):
            recent_decisions = self.shared_context.decision_path.get_recent_decisions(n=5)
            if recent_decisions:
                info_parts.append("\n## Recent Work:\n")
                for decision in recent_decisions:
                    info_parts.append(f"- {decision.reasoning}")

        return "\n".join(info_parts)

    def _extract_code_artifacts(self) -> list[str]:
        """从 shared_context 提取代码文件

        Returns:
            list: 代码文件路径列表
        """
        if not self.shared_context or not hasattr(self.shared_context, 'artifact_manager'):
            return []

        code_artifacts = self.shared_context.artifact_manager.get_artifacts_by_type("code")
        return [artifact.path for artifact in code_artifacts]

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名

        Args:
            filename: 原始文件名

        Returns:
            str: 清理后的文件名
        """
        # 移除非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 替换空格
        filename = filename.replace(' ', '_')
        # 限制长度
        return filename[:100]

    async def _handle_general_task(self, user_input: str) -> str:
        """处理通用任务（使用 LLM）

        Args:
            user_input: 用户输入

        Returns:
            str: 处理结果
        """
        # 默认生成研究报告
        return await self.generate_research_report(
            topic=user_input,
            report_type="detailed",
        )

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
