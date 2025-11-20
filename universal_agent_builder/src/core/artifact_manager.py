"""Artifact Manager for managing files produced by agents"""

import os
import json
from pathlib import Path
from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field


ArtifactType = Literal["document", "code", "media", "data", "other"]


class ArtifactMetadata(BaseModel):
    """文件元信息"""

    path: str = Field(description="文件相对路径（相对于 session 目录）")

    type: ArtifactType = Field(description="文件类型")

    summary: str = Field(description="文件内容摘要")

    producer: str = Field(description="产生该文件的 Agent 或工具名称")

    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="创建时间",
    )

    size_bytes: int | None = Field(
        default=None,
        description="文件大小（字节）",
    )

    tags: list[str] = Field(
        default_factory=list,
        description="标签，用于分类和搜索",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="额外的元信息",
    )

    def to_summary_line(self) -> str:
        """生成单行摘要"""
        return f"[{self.type}] {self.path}: {self.summary} (by {self.producer})"


class ArtifactManager:
    """Artifact 管理器

    负责：
    - 索引文件元信息
    - 提供文件查询接口
    - 生成文件索引摘要用于 Prompt
    """

    def __init__(self, session_dir: str | Path):
        """初始化 Artifact Manager

        Args:
            session_dir: Session 根目录路径
        """
        self.session_dir = Path(session_dir)
        self.artifacts_dir = self.session_dir / "artifacts"
        self.index_file = self.session_dir / "context" / "artifacts_index.json"

        # 文件索引: {relative_path: ArtifactMetadata}
        self.index: dict[str, ArtifactMetadata] = {}

        # 确保目录存在
        self._ensure_directories()

        # 加载已有索引
        self._load_index()

    def _ensure_directories(self):
        """确保必要的目录存在"""
        (self.artifacts_dir / "documents").mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "code").mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "media").mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "data").mkdir(parents=True, exist_ok=True)
        (self.session_dir / "context").mkdir(parents=True, exist_ok=True)

    def _load_index(self):
        """从文件加载索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.index = {
                        path: ArtifactMetadata.model_validate(meta)
                        for path, meta in data.items()
                    }
            except Exception as e:
                print(f"Warning: Failed to load index: {e}")
                self.index = {}

    def _save_index(self):
        """保存索引到文件"""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                data = {path: meta.model_dump() for path, meta in self.index.items()}
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error: Failed to save index: {e}")

    def register_artifact(
        self,
        path: str | Path,
        artifact_type: ArtifactType,
        summary: str,
        producer: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactMetadata:
        """注册新文件

        Args:
            path: 文件路径（可以是绝对路径或相对路径）
            artifact_type: 文件类型
            summary: 文件摘要
            producer: 产生者
            tags: 标签
            metadata: 额外元信息

        Returns:
            ArtifactMetadata: 文件元信息
        """
        # 转换为相对路径
        path = Path(path)
        if path.is_absolute():
            try:
                rel_path = path.relative_to(self.session_dir)
            except ValueError:
                # 如果不在 session_dir 下，使用绝对路径
                rel_path = path
        else:
            rel_path = path

        # 获取文件大小
        size_bytes = None
        if path.exists():
            size_bytes = path.stat().st_size

        # 创建元信息
        artifact = ArtifactMetadata(
            path=str(rel_path),
            type=artifact_type,
            summary=summary,
            producer=producer,
            size_bytes=size_bytes,
            tags=tags or [],
            metadata=metadata or {},
        )

        # 添加到索引
        self.index[str(rel_path)] = artifact

        # 保存索引
        self._save_index()

        return artifact

    def get_artifact(self, path: str) -> ArtifactMetadata | None:
        """获取文件元信息

        Args:
            path: 文件路径

        Returns:
            ArtifactMetadata | None: 文件元信息，不存在则返回 None
        """
        return self.index.get(path)

    def get_artifacts_by_type(
        self, artifact_type: ArtifactType
    ) -> list[ArtifactMetadata]:
        """获取指定类型的所有文件

        Args:
            artifact_type: 文件类型

        Returns:
            list[ArtifactMetadata]: 文件列表
        """
        return [a for a in self.index.values() if a.type == artifact_type]

    def get_artifacts_by_producer(self, producer: str) -> list[ArtifactMetadata]:
        """获取指定产生者的所有文件

        Args:
            producer: 产生者名称

        Returns:
            list[ArtifactMetadata]: 文件列表
        """
        return [a for a in self.index.values() if a.producer == producer]

    def get_artifacts_by_tag(self, tag: str) -> list[ArtifactMetadata]:
        """获取包含指定标签的所有文件

        Args:
            tag: 标签

        Returns:
            list[ArtifactMetadata]: 文件列表
        """
        return [a for a in self.index.values() if tag in a.tags]

    def search_artifacts(self, keyword: str) -> list[ArtifactMetadata]:
        """搜索文件（在路径和摘要中搜索关键词）

        Args:
            keyword: 关键词

        Returns:
            list[ArtifactMetadata]: 匹配的文件列表
        """
        keyword_lower = keyword.lower()
        results = []
        for artifact in self.index.values():
            if (
                keyword_lower in artifact.path.lower()
                or keyword_lower in artifact.summary.lower()
            ):
                results.append(artifact)
        return results

    def format_index_for_prompt(
        self, max_items: int = 20, filter_type: ArtifactType | None = None
    ) -> str:
        """格式化文件索引用于 Prompt

        Args:
            max_items: 最多显示的文件数
            filter_type: 可选，只显示特定类型的文件

        Returns:
            str: 格式化的索引
        """
        artifacts = list(self.index.values())

        if filter_type:
            artifacts = [a for a in artifacts if a.type == filter_type]

        if not artifacts:
            return "No artifacts available."

        # 按创建时间倒序
        artifacts.sort(key=lambda a: a.created_at, reverse=True)

        # 限制数量
        artifacts = artifacts[:max_items]

        # 按类型分组
        by_type: dict[str, list[ArtifactMetadata]] = {}
        for artifact in artifacts:
            if artifact.type not in by_type:
                by_type[artifact.type] = []
            by_type[artifact.type].append(artifact)

        # 格式化输出
        lines = [f"Available Artifacts ({len(artifacts)} total):"]
        for artifact_type, items in sorted(by_type.items()):
            lines.append(f"\n## {artifact_type.upper()} ({len(items)})")
            for item in items:
                lines.append(f"  - {item.to_summary_line()}")

        return "\n".join(lines)

    def get_absolute_path(self, relative_path: str) -> Path:
        """将相对路径转换为绝对路径

        Args:
            relative_path: 相对路径

        Returns:
            Path: 绝对路径
        """
        return self.session_dir / relative_path

    def clear_index(self):
        """清空索引（不删除实际文件）"""
        self.index.clear()
        self._save_index()

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息

        Returns:
            dict: 统计信息
        """
        total_size = sum(
            a.size_bytes for a in self.index.values() if a.size_bytes is not None
        )
        by_type = {}
        for artifact in self.index.values():
            if artifact.type not in by_type:
                by_type[artifact.type] = 0
            by_type[artifact.type] += 1

        return {
            "total_artifacts": len(self.index),
            "total_size_bytes": total_size,
            "by_type": by_type,
        }
