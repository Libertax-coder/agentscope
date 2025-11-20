"""Docker Manager - 管理 Docker 容器的创建、运行和销毁"""

import time
from pathlib import Path
from typing import Any, Literal

try:
    import docker
    from docker.models.containers import Container
    from docker.errors import DockerException, ImageNotFound
except ImportError:
    docker = None
    Container = None
    DockerException = Exception
    ImageNotFound = Exception


class DockerManager:
    """Docker 容器管理器

    负责：
    - 创建和管理 Session 专属容器
    - 容器生命周期管理
    - 资源限制配置
    - 文件系统访问
    """

    def __init__(
        self,
        image_name: str = "universal-agent-sandbox:latest",
        base_workspace: str | Path = "/tmp/universal_agent_workspaces",
    ):
        """初始化 Docker Manager

        Args:
            image_name: Docker 镜像名称
            base_workspace: 主机上的工作空间基础目录
        """
        if docker is None:
            raise ImportError(
                "Docker Manager requires 'docker' package. "
                "Install with: pip install docker"
            )

        self.image_name = image_name
        self.base_workspace = Path(base_workspace)
        self.base_workspace.mkdir(parents=True, exist_ok=True)

        try:
            self.client = docker.from_env()
            print(f"[DockerManager] Connected to Docker daemon")
        except DockerException as e:
            raise RuntimeError(
                f"Failed to connect to Docker daemon: {e}\n"
                "Make sure Docker is running and accessible."
            )

        # 确保镜像存在
        self._ensure_image()

    def _ensure_image(self):
        """确保 Docker 镜像存在"""
        try:
            self.client.images.get(self.image_name)
            print(f"[DockerManager] Image '{self.image_name}' found")
        except ImageNotFound:
            print(f"[DockerManager] Image '{self.image_name}' not found")
            print(f"[DockerManager] Please build the image first:")
            print(f"  cd universal_agent_builder")
            print(f"  docker build -t {self.image_name} .")
            raise RuntimeError(
                f"Docker image '{self.image_name}' not found. "
                "Please build it first."
            )

    def create_container(
        self,
        session_id: str,
        cpu_limit: float = 2.0,
        memory_limit: str = "4g",
        timeout_hours: int = 2,
        network_mode: str = "bridge",
    ) -> Container:
        """创建 Session 专属容器

        Args:
            session_id: Session ID
            cpu_limit: CPU 限制（核心数）
            memory_limit: 内存限制（如 "4g", "2g"）
            timeout_hours: 超时时间（小时）
            network_mode: 网络模式

        Returns:
            Container: Docker 容器对象
        """
        # 创建 Session 工作目录
        session_workspace = self.base_workspace / f"session_{session_id}"
        session_workspace.mkdir(parents=True, exist_ok=True)

        # 容器名称
        container_name = f"universal_agent_session_{session_id}"

        # 容器配置
        container_config = {
            "image": self.image_name,
            "name": container_name,
            "detach": True,
            "tty": True,
            "stdin_open": True,
            # 挂载 Session 工作目录（注意：这是可选的，根据需求决定是否挂载）
            # "volumes": {
            #     str(session_workspace): {
            #         "bind": "/workspace",
            #         "mode": "rw",
            #     }
            # },
            "working_dir": "/workspace",
            "network_mode": network_mode,
            # 资源限制
            "cpu_quota": int(cpu_limit * 100000),  # CPU 限制
            "cpu_period": 100000,
            "mem_limit": memory_limit,
            # 环境变量
            "environment": {
                "SESSION_ID": session_id,
                "PYTHONUNBUFFERED": "1",
            },
            # 自动删除（可选）
            "auto_remove": False,
        }

        try:
            container = self.client.containers.run(**container_config)
            print(f"[DockerManager] Container '{container_name}' created")
            print(f"[DockerManager]   CPU limit: {cpu_limit} cores")
            print(f"[DockerManager]   Memory limit: {memory_limit}")
            print(f"[DockerManager]   Timeout: {timeout_hours} hours")

            return container

        except Exception as e:
            raise RuntimeError(f"Failed to create container: {e}")

    def execute_command(
        self,
        container: Container,
        command: str | list[str],
        workdir: str | None = None,
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        """在容器中执行命令

        Args:
            container: 容器对象
            command: 命令（字符串或列表）
            workdir: 工作目录
            timeout: 超时时间（秒）

        Returns:
            tuple[int, str, str]: (exit_code, stdout, stderr)
        """
        try:
            exec_config = {
                "cmd": command,
                "stdout": True,
                "stderr": True,
                "stdin": False,
            }

            if workdir:
                exec_config["workdir"] = workdir

            exec_result = container.exec_run(**exec_config)

            exit_code = exec_result.exit_code
            output = exec_result.output.decode("utf-8", errors="replace")

            # 简单分离 stdout 和 stderr（实际可能需要更复杂的处理）
            stdout = output
            stderr = "" if exit_code == 0 else output

            return exit_code, stdout, stderr

        except Exception as e:
            return 1, "", f"Error executing command: {str(e)}"

    def copy_to_container(
        self,
        container: Container,
        src_path: str | Path,
        dest_path: str,
    ):
        """复制文件到容器

        Args:
            container: 容器对象
            src_path: 源文件路径（主机）
            dest_path: 目标路径（容器内）
        """
        import tarfile
        import io

        src_path = Path(src_path)

        # 创建 tar 归档
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(src_path, arcname=src_path.name)

        tar_stream.seek(0)

        # 复制到容器
        container.put_archive(dest_path, tar_stream.getvalue())

    def copy_from_container(
        self,
        container: Container,
        src_path: str,
        dest_path: str | Path,
    ):
        """从容器复制文件

        Args:
            container: 容器对象
            src_path: 源路径（容器内）
            dest_path: 目标文件路径（主机）
        """
        import tarfile
        import io

        # 获取文件
        bits, stat = container.get_archive(src_path)

        # 解压 tar
        tar_stream = io.BytesIO(b"".join(bits))
        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            tar.extractall(dest_path)

    def stop_container(self, container: Container, timeout: int = 10):
        """停止容器

        Args:
            container: 容器对象
            timeout: 超时时间（秒）
        """
        try:
            container.stop(timeout=timeout)
            print(f"[DockerManager] Container '{container.name}' stopped")
        except Exception as e:
            print(f"[DockerManager] Error stopping container: {e}")

    def remove_container(self, container: Container, force: bool = False):
        """删除容器

        Args:
            container: 容器对象
            force: 是否强制删除
        """
        try:
            container.remove(force=force)
            print(f"[DockerManager] Container '{container.name}' removed")
        except Exception as e:
            print(f"[DockerManager] Error removing container: {e}")

    def get_container_logs(
        self,
        container: Container,
        tail: int | str = "all",
    ) -> str:
        """获取容器日志

        Args:
            container: 容器对象
            tail: 日志行数

        Returns:
            str: 日志内容
        """
        logs = container.logs(tail=tail).decode("utf-8", errors="replace")
        return logs

    def get_container_stats(self, container: Container) -> dict[str, Any]:
        """获取容器统计信息

        Args:
            container: 容器对象

        Returns:
            dict: 统计信息
        """
        stats = container.stats(stream=False)
        return stats

    def list_containers(
        self,
        all_containers: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[Container]:
        """列出容器

        Args:
            all_containers: 是否包含停止的容器
            filters: 过滤条件

        Returns:
            list[Container]: 容器列表
        """
        return self.client.containers.list(all=all_containers, filters=filters)

    def cleanup_session_containers(self, session_id: str | None = None):
        """清理 Session 容器

        Args:
            session_id: Session ID（如果为 None，清理所有 universal_agent 容器）
        """
        if session_id:
            filters = {"name": f"universal_agent_session_{session_id}"}
        else:
            filters = {"name": "universal_agent_session_"}

        containers = self.list_containers(all_containers=True, filters=filters)

        for container in containers:
            print(f"[DockerManager] Cleaning up container '{container.name}'...")
            self.stop_container(container, timeout=5)
            self.remove_container(container, force=True)

        print(f"[DockerManager] Cleanup completed: {len(containers)} containers removed")
