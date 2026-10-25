from __future__ import annotations

from pathlib import Path


def build_brain_report(
    project_name: str,
    project_path: Path,
    stats: dict,
    diagnostics: list[dict],
    graph_data: dict,
) -> str:
    top_types: dict[str, int] = {}
    for node in graph_data.get("nodes", []):
        node_type = str(node.get("type", "unknown"))
        top_types[node_type] = top_types.get(node_type, 0) + 1
    lines = [
        f"# BrainGraph Report: {project_name}",
        "",
        f"- Project path: `{project_path}`",
        f"- Total files: `{stats.get('total_files', 0)}`",
        f"- Raw tokens: `{stats.get('raw_tokens', 0)}`",
        f"- File-summary tokens: `{stats.get('summary_tokens', 0)}`",
        f"- Summary-size reduction: `{stats.get('summary_reduction_percent', 0)}%` (summaries vs. indexed source; not query or provider token savings)",
        f"- Graph nodes: `{len(graph_data.get('nodes', []))}`",
        f"- Graph edges: `{len(graph_data.get('edges', []))}`",
        "",
        "## Node Types",
        "",
    ]
    for node_type, count in sorted(top_types.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{node_type}`: {count}")
    lines.extend(["", "## Diagnostics", ""])
    if diagnostics:
        for item in diagnostics:
            location = f" ({item['file_path']})" if item.get("file_path") else ""
            lines.append(f"- **{item['severity']}** `{item['code']}`{location}: {item['message']}")
    else:
        lines.append("- No diagnostics reported.")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `graph.json`: structured graph export",
            "- `graph.html`: local static viewer",
            "- `summaries/`: file-level summaries",
            "- `memory.db`: metadata, files, relations, summaries",
            "- `embeddings.db`: vector or lexical retrieval cache",
        ]
    )
    return "\n".join(lines) + "\n"
