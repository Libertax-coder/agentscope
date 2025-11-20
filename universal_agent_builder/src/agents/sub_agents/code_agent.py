"""Code Agent - 代码交付智能体

负责所有编程任务：代码执行、生成、测试、可视化
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal

from agentscope.agent import AgentBase
from agentscope.message import Msg


class CodeAgent(AgentBase):
    """代码交付智能体

    职责：
    - 执行 Python/JavaScript 代码
    - 生成代码文件
    - 数据可视化（生成图表）
    - 测试执行
    - 包安装

    支持独立调用和交互式调用两种模式
    """

    def __init__(
        self,
        name: str = "CodeAgent",
        model_config_name: str | None = None,
        workspace_dir: str | Path | None = None,
        **kwargs: Any,
    ):
        """初始化 Code Agent

        Args:
            name: Agent 名称
            model_config_name: 模型配置名称
            workspace_dir: 工作目录（用于存储代码和输出）
            **kwargs: 其他参数
        """
        super().__init__()

        self.name = name
        self.model_config_name = model_config_name

        # 工作目录
        if workspace_dir is None:
            workspace_dir = Path.cwd() / "workspace" / "code_agent"
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

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
        if task_type == "execute_python":
            result = await self.execute_python_code(
                code=task_info.get("code", ""),
                description=task_info.get("description", ""),
            )
        elif task_type == "generate_chart":
            result = await self.generate_chart(
                data=task_info.get("data", {}),
                chart_type=task_info.get("chart_type", "bar"),
                title=task_info.get("title", "Chart"),
            )
        elif task_type == "write_code_file":
            result = await self.write_code_file(
                filename=task_info.get("filename", "code.py"),
                code=task_info.get("code", ""),
                language=task_info.get("language", "python"),
            )
        elif task_type == "generate_code":
            result = await self.generate_code(
                requirement=task_info.get("requirement", ""),
                language=task_info.get("language", "python"),
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
        if "execute" in user_input.lower() and "python" in user_input.lower():
            return {"task_type": "execute_python", "description": user_input}
        elif "chart" in user_input.lower() or "plot" in user_input.lower():
            return {"task_type": "generate_chart", "description": user_input}
        elif "write" in user_input.lower() and "file" in user_input.lower():
            return {"task_type": "write_code_file", "description": user_input}
        elif "generate" in user_input.lower() and "code" in user_input.lower():
            return {"task_type": "generate_code", "requirement": user_input}
        else:
            return {"task_type": "general", "description": user_input}

    async def execute_python_code(
        self,
        code: str,
        description: str = "",
        save_output: bool = True,
    ) -> str:
        """执行 Python 代码

        Args:
            code: Python 代码
            description: 代码描述
            save_output: 是否保存输出到文件

        Returns:
            str: 执行结果
        """
        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            dir=self.workspace_dir,
            delete=False,
        ) as f:
            f.write(code)
            code_file = Path(f.name)

        try:
            # 执行代码
            result = subprocess.run(
                ["python", str(code_file)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace_dir,
            )

            output = result.stdout
            error = result.stderr

            if result.returncode == 0:
                response = f"Code executed successfully.\n\nOutput:\n{output}"

                # 保存输出
                if save_output and output:
                    output_file = self.workspace_dir / "output.txt"
                    output_file.write_text(output)
                    self._register_artifact(
                        path=str(output_file),
                        artifact_type="data",
                        summary=f"Execution output: {description or 'Python code'}",
                    )
                    response += f"\n\nOutput saved to: {output_file}"

                return response
            else:
                return f"Code execution failed.\n\nError:\n{error}"

        except subprocess.TimeoutExpired:
            return "Code execution timed out (30s limit)."
        except Exception as e:
            return f"Error executing code: {str(e)}"
        finally:
            # 清理临时文件
            code_file.unlink(missing_ok=True)

    async def generate_chart(
        self,
        data: dict[str, Any] | list[Any],
        chart_type: Literal["bar", "line", "pie", "scatter"] = "bar",
        title: str = "Chart",
        xlabel: str = "",
        ylabel: str = "",
    ) -> str:
        """生成图表

        Args:
            data: 数据（字典或列表）
            chart_type: 图表类型
            title: 图表标题
            xlabel: X 轴标签
            ylabel: Y 轴标签

        Returns:
            str: 结果消息（包含图片路径）
        """
        try:
            # 生成绘图代码
            plot_code = self._generate_plot_code(
                data, chart_type, title, xlabel, ylabel
            )

            # 执行绘图代码
            output_file = self.workspace_dir / "media" / f"{title.replace(' ', '_').lower()}.png"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            plot_code = plot_code.replace("OUTPUT_PATH", str(output_file))

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=self.workspace_dir,
                delete=False,
            ) as f:
                f.write(plot_code)
                code_file = Path(f.name)

            result = subprocess.run(
                ["python", str(code_file)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace_dir,
            )

            code_file.unlink(missing_ok=True)

            if result.returncode == 0 and output_file.exists():
                self._register_artifact(
                    path=str(output_file),
                    artifact_type="media",
                    summary=f"{chart_type.capitalize()} chart: {title}",
                )
                return f"Chart generated successfully: {output_file}"
            else:
                return f"Failed to generate chart.\nError: {result.stderr}"

        except Exception as e:
            return f"Error generating chart: {str(e)}"

    def _generate_plot_code(
        self,
        data: dict | list,
        chart_type: str,
        title: str,
        xlabel: str,
        ylabel: str,
    ) -> str:
        """生成绘图代码

        Args:
            data: 数据
            chart_type: 图表类型
            title: 标题
            xlabel: X 轴标签
            ylabel: Y 轴标签

        Returns:
            str: Python 绘图代码
        """
        code = f"""
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 非交互式后端

# 数据
data = {repr(data)}

# 创建图表
plt.figure(figsize=(10, 6))
"""

        if chart_type == "bar":
            if isinstance(data, dict):
                code += f"""
plt.bar(list(data.keys()), list(data.values()))
"""
            else:
                code += f"""
plt.bar(range(len(data)), data)
"""

        elif chart_type == "line":
            if isinstance(data, dict):
                code += f"""
plt.plot(list(data.keys()), list(data.values()), marker='o')
"""
            else:
                code += f"""
plt.plot(data, marker='o')
"""

        elif chart_type == "pie":
            if isinstance(data, dict):
                code += f"""
plt.pie(list(data.values()), labels=list(data.keys()), autopct='%1.1f%%')
"""
            else:
                code += f"""
plt.pie(data, autopct='%1.1f%%')
"""

        elif chart_type == "scatter":
            if isinstance(data, dict):
                code += f"""
plt.scatter(list(data.keys()), list(data.values()))
"""
            else:
                code += f"""
plt.scatter(range(len(data)), data)
"""

        code += f"""
plt.title('{title}')
"""
        if xlabel:
            code += f"plt.xlabel('{xlabel}')\n"
        if ylabel:
            code += f"plt.ylabel('{ylabel}')\n"

        code += """
plt.tight_layout()
plt.savefig('OUTPUT_PATH', dpi=100, bbox_inches='tight')
plt.close()
"""

        return code

    async def write_code_file(
        self,
        filename: str,
        code: str,
        language: str = "python",
    ) -> str:
        """写入代码文件

        Args:
            filename: 文件名
            code: 代码内容
            language: 编程语言

        Returns:
            str: 结果消息
        """
        # 确定文件路径
        code_dir = self.workspace_dir / "code"
        code_dir.mkdir(parents=True, exist_ok=True)

        file_path = code_dir / filename

        try:
            file_path.write_text(code, encoding="utf-8")

            self._register_artifact(
                path=str(file_path),
                artifact_type="code",
                summary=f"{language.capitalize()} code: {filename}",
            )

            return f"Code file written successfully: {file_path}"

        except Exception as e:
            return f"Error writing code file: {str(e)}"

    async def generate_code(
        self,
        requirement: str,
        language: str = "python",
    ) -> str:
        """使用 LLM 生成代码

        Args:
            requirement: 需求描述
            language: 编程语言

        Returns:
            str: 生成的代码或错误消息
        """
        prompt = f"""Generate {language} code based on the following requirement:

Requirement:
{requirement}

Please output only the code, without any explanation or markdown formatting.
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        # 提取代码
        code = self._extract_code(response.text, language)

        if code:
            # 保存到文件
            filename = f"generated_code.{self._get_file_extension(language)}"
            await self.write_code_file(filename, code, language)

            return f"Code generated and saved to: {filename}\n\nCode:\n{code}"
        else:
            return f"Failed to generate code.\nResponse: {response.text}"

    def _extract_code(self, text: str, language: str) -> str:
        """从文本中提取代码

        Args:
            text: 文本
            language: 编程语言

        Returns:
            str: 提取的代码
        """
        # 尝试提取代码块
        pattern = rf"```{language}\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试提取通用代码块
        pattern = r"```\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 返回全部文本
        return text.strip()

    def _get_file_extension(self, language: str) -> str:
        """获取文件扩展名

        Args:
            language: 编程语言

        Returns:
            str: 文件扩展名
        """
        extensions = {
            "python": "py",
            "javascript": "js",
            "typescript": "ts",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "go": "go",
            "rust": "rs",
        }
        return extensions.get(language.lower(), "txt")

    async def _handle_general_task(self, user_input: str) -> str:
        """处理通用任务（使用 LLM）

        Args:
            user_input: 用户输入

        Returns:
            str: 处理结果
        """
        prompt = f"""You are a code agent. The user has requested:

{user_input}

Analyze the request and provide a solution. If you need to execute code or generate files, describe what you would do.
"""

        response = await self.model(Msg(name=self.name, content=prompt, role="assistant"))

        return response.text

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
