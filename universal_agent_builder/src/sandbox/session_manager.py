"""Session Manager - 管理 Session 的完整生命周期"""

import shortuuid
from pathlib import Path
from typing import Any
from datetime import datetime

from .docker_manager import DockerManager
from ..core.context import MasterContext


class Session:
    """Session 对象

    表示一个独立的工作会话，包含：
    - 唯一的 Session ID
    - Docker 容器
    - Master Context
    - 创建和更新时间
    """

    def __init__(
        self,
        session_id: str,
        container: Any,  # Docker Container
        context: MasterContext,
        workspace_dir: Path,
        created_at: str | None = None,
    ):
        """初始化 Session

        Args:
            session_id: Session ID
            container: Docker 容器
            context: Master Context
            workspace_dir: 工作目录
            created_at: 创建时间
        """
        self.session_id = session_id
        self.container = container
        self.context = context
        self.workspace_dir = workspace_dir
        self.created_at = created_at or datetime.now().isoformat()
        self.last_updated = self.created_at

    def update_timestamp(self):
        """更新最后活动时间"""
        self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            dict: Session 信息
        """
        return {
            "session_id": self.session_id,
            "container_id": self.container.id if self.container else None,
            "container_name": self.container.name if self.container else None,
            "workspace_dir": str(self.workspace_dir),
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "context_stats": self.context.get_stats() if self.context else {},
        }


class SessionManager:
    """Session 管理器

    负责：
    - 创建和销毁 Session
    - 管理 Session 生命周期
    - 集成 Docker 容器和 Context
    - Session 状态持久化
    """

    def __init__(
        self,
        docker_manager: DockerManager | None = None,
        base_workspace: str | Path = "/tmp/universal_agent_sessions",
        enable_docker: bool = True,
    ):
        """初始化 Session Manager

        Args:
            docker_manager: Docker Manager 实例
            base_workspace: 工作空间基础目录
            enable_docker: 是否启用 Docker（False 时仅使用本地文件系统）
        """
        self.enable_docker = enable_docker
        self.base_workspace = Path(base_workspace)
        self.base_workspace.mkdir(parents=True, exist_ok=True)

        # Docker Manager
        if enable_docker:
            self.docker_manager = docker_manager or DockerManager(
                base_workspace=self.base_workspace
            )
        else:
            self.docker_manager = None
            print("[SessionManager] Running without Docker (local mode)")

        # Active sessions
        self.sessions: dict[str, Session] = {}

    def create_session(
        self,
        session_id: str | None = None,
        cpu_limit: float = 2.0,
        memory_limit: str = "4g",
    ) -> Session:
        """创建新 Session

        Args:
            session_id: Session ID（如果为 None，自动生成）
            cpu_limit: CPU 限制
            memory_limit: 内存限制

        Returns:
            Session: 新创建的 Session
        """
        # 生成 Session ID
        if session_id is None:
            session_id = shortuuid.uuid()[:12]

        # 创建工作目录
        workspace_dir = self.base_workspace / f"session_{session_id}"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # 创建 Docker 容器（如果启用）
        container = None
        if self.enable_docker and self.docker_manager:
            try:
                container = self.docker_manager.create_container(
                    session_id=session_id,
                    cpu_limit=cpu_limit,
                    memory_limit=memory_limit,
                )
            except Exception as e:
                print(f"[SessionManager] Warning: Failed to create Docker container: {e}")
                print(f"[SessionManager] Falling back to local mode")

        # 创建 Master Context
        context = MasterContext(session_dir=workspace_dir)

        # 创建 Session 对象
        session = Session(
            session_id=session_id,
            container=container,
            context=context,
            workspace_dir=workspace_dir,
        )

        # 添加到 active sessions
        self.sessions[session_id] = session

        print(f"[SessionManager] Session '{session_id}' created")
        if container:
            print(f"[SessionManager]   Container: {container.name}")
        print(f"[SessionManager]   Workspace: {workspace_dir}")

        return session

    def get_session(self, session_id: str) -> Session | None:
        """获取 Session

        Args:
            session_id: Session ID

        Returns:
            Session | None: Session 对象
        """
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        """列出所有活跃的 Session

        Returns:
            list[Session]: Session 列表
        """
        return list(self.sessions.values())

    def execute_in_session(
        self,
        session_id: str,
        command: str | list[str],
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        """在 Session 容器中执行命令

        Args:
            session_id: Session ID
            command: 命令
            timeout: 超时时间

        Returns:
            tuple[int, str, str]: (exit_code, stdout, stderr)
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        if not session.container:
            raise RuntimeError(f"Session '{session_id}' has no Docker container")

        # 执行命令
        result = self.docker_manager.execute_command(
            container=session.container,
            command=command,
            timeout=timeout,
        )

        # 更新时间戳
        session.update_timestamp()

        return result

    def save_session_state(self, session_id: str):
        """保存 Session 状态

        Args:
            session_id: Session ID
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        # 保存 Context
        session.context.save_context()

        # 保存 Session 元数据
        metadata_file = session.workspace_dir / "session_metadata.json"
        import json

        with open(metadata_file, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

        print(f"[SessionManager] Session '{session_id}' state saved")

    def close_session(self, session_id: str, save_state: bool = True):
        """关闭 Session

        Args:
            session_id: Session ID
            save_state: 是否保存状态
        """
        session = self.get_session(session_id)
        if not session:
            print(f"[SessionManager] Session '{session_id}' not found")
            return

        # 保存状态
        if save_state:
            self.save_session_state(session_id)

        # 停止和删除容器
        if session.container and self.docker_manager:
            self.docker_manager.stop_container(session.container, timeout=5)
            self.docker_manager.remove_container(session.container, force=True)

        # 从活跃列表移除
        del self.sessions[session_id]

        print(f"[SessionManager] Session '{session_id}' closed")

    def cleanup_all_sessions(self):
        """清理所有 Session"""
        session_ids = list(self.sessions.keys())

        for session_id in session_ids:
            self.close_session(session_id, save_state=False)

        print(f"[SessionManager] All sessions cleaned up: {len(session_ids)} sessions")

    def get_session_stats(self, session_id: str) -> dict[str, Any]:
        """获取 Session 统计信息

        Args:
            session_id: Session ID

        Returns:
            dict: 统计信息
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        stats = session.to_dict()

        # 添加容器统计信息
        if session.container and self.docker_manager:
            try:
                container_stats = self.docker_manager.get_container_stats(
                    session.container
                )
                stats["container_stats"] = container_stats
            except Exception as e:
                stats["container_stats"] = {"error": str(e)}

        return stats
