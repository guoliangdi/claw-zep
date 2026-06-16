"""
记忆树导出
==========
导出为 Markdown / Obsidian（YAML frontmatter + [[wikilink]]）。
返回 {相对路径: 文件内容}，由上层写入对象存储或打包 zip。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.memory_tree.service import MemoryTreeService, _loads_refs
from models.memory_tree import MemoryTreeNode

_SAFE = re.compile(r'[\\/:*?"<>|]+')


def _safe_filename(title: str, node_id: str) -> str:
    base = _SAFE.sub("_", title).strip()[:60] or "node"
    return f"{base}__{node_id[:8]}.md"


def _frontmatter(node: MemoryTreeNode) -> str:
    refs = _loads_refs(node.entity_refs_json)
    lines = [
        "---",
        f"id: {node.id}",
        f"layer: {node.tree_layer}",
        f"title: {node.title}",
        f"version: {node.version}",
        f"valid_from: {node.valid_from.isoformat() if node.valid_from else ''}",
        f"valid_until: {node.valid_until.isoformat() if node.valid_until else ''}",
        f"status: {node.status}",
    ]
    if node.topic_label:
        lines.append(f"topic: {node.topic_label}")
    if refs:
        lines.append("entities:")
        for r in refs:
            lines.append(f"  - {r}")
    lines.append("---")
    return "\n".join(lines)


def render_node(
    node: MemoryTreeNode,
    obsidian: bool = True,
    entity_name_map: Optional[Dict[str, str]] = None,
    child_titles: Optional[List[str]] = None,
) -> str:
    """渲染单节点为 Markdown 文本。"""
    parts = [_frontmatter(node), "", f"# {node.title}", ""]
    if node.summary:
        parts += ["> [!summary] 摘要", f"> {node.summary}", ""]
    if node.content_markdown:
        parts += [node.content_markdown, ""]

    if obsidian:
        refs = _loads_refs(node.entity_refs_json)
        if refs:
            parts.append("## 关联实体")
            for r in refs:
                name = (entity_name_map or {}).get(r, r)
                parts.append(f"- [[{name}]]")
            parts.append("")
        if child_titles:
            parts.append("## 子节点")
            for t in child_titles:
                parts.append(f"- [[{t}]]")
            parts.append("")
    return "\n".join(parts)


class MemoryTreeExporter:
    @staticmethod
    async def export(
        db: AsyncSession,
        project_id: str,
        tree_layer: Optional[str] = None,
        fmt: str = "obsidian",
        entity_name_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """导出节点为 {路径: 内容}。fmt: obsidian|markdown。"""
        obsidian = fmt == "obsidian"
        layers = [tree_layer] if tree_layer else ["source", "topic", "global"]
        files: Dict[str, str] = {}
        children_index: Dict[str, List[MemoryTreeNode]] = {}

        all_nodes: List[MemoryTreeNode] = []
        for layer in layers:
            nodes = await MemoryTreeService.list_nodes(db, project_id, tree_layer=layer)
            all_nodes.extend(nodes)

        title_by_id = {n.id: n.title for n in all_nodes}
        for n in all_nodes:
            if n.parent_id:
                children_index.setdefault(n.parent_id, []).append(n)

        for n in all_nodes:
            child_titles = [c.title for c in children_index.get(n.id, [])]
            content = render_node(
                n, obsidian=obsidian, entity_name_map=entity_name_map,
                child_titles=child_titles,
            )
            folder = n.tree_layer
            files[f"{folder}/{_safe_filename(n.title, n.id)}"] = content

        # 索引文件
        if files:
            idx = ["# 记忆树导出索引", ""]
            for layer in layers:
                idx.append(f"## {layer}")
                for n in all_nodes:
                    if n.tree_layer == layer:
                        idx.append(f"- [[{n.title}]]")
                idx.append("")
            files["index.md"] = "\n".join(idx)
        return files


memory_tree_exporter = MemoryTreeExporter()
