from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from braingraph.database.models import CodeFile, Relation, Symbol


class GraphEngine:
    def __init__(self, session: Session, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    def build(self) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        files = self.session.scalars(
            select(CodeFile).where(CodeFile.project_id == self.project_id)
        ).all()
        for file in files:
            graph.add_node(
                f"file:{file.path}",
                id=f"file:{file.path}",
                label=file.path,
                type="file",
                language=file.language,
                tokens=file.token_estimate,
            )
        symbols = self.session.scalars(
            select(Symbol).where(Symbol.project_id == self.project_id)
        ).all()
        for symbol in symbols:
            file = next((item for item in files if item.id == symbol.file_id), None)
            node_id = f"{symbol.kind}:{symbol.name}:{symbol.file_id}"
            graph.add_node(
                node_id,
                id=node_id,
                label=symbol.name,
                type=symbol.kind,
                line_start=symbol.line_start,
                line_end=symbol.line_end,
            )
            if file:
                graph.add_edge(
                    f"file:{file.path}",
                    node_id,
                    type="contains",
                    confidence=1.0,
                )
        relations = self.session.scalars(
            select(Relation).where(Relation.project_id == self.project_id)
        ).all()
        for relation in relations:
            source = f"{relation.source_type}:{relation.source_key}"
            target = f"{relation.target_type}:{relation.target_key}"
            graph.add_node(source, id=source, label=relation.source_key, type=relation.source_type)
            graph.add_node(target, id=target, label=relation.target_key, type=relation.target_type)
            graph.add_edge(
                source,
                target,
                type=relation.relation_type,
                confidence=relation.confidence,
                metadata=json.loads(relation.metadata_json or "{}"),
            )
        return graph

    def export(self, output_path: Path | None = None) -> dict[str, list[dict]]:
        graph = self.build()
        data = {
            "nodes": [dict(attrs) for _, attrs in graph.nodes(data=True)],
            "edges": [
                {"source": source, "target": target, **attrs}
                for source, target, attrs in graph.edges(data=True)
            ],
        }
        if output_path:
            output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def export_html(self, output_path: Path) -> Path:
        data = self.export()
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BrainGraph</title>
  <style>
    body {{ margin: 0; background: #0a0b0f; color: #f5f7fb; font-family: Inter, Arial, sans-serif; }}
    header {{ padding: 16px 20px; border-bottom: 1px solid #20242f; display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    input {{ width: min(420px, 100%); padding: 10px 12px; border-radius: 6px; border: 1px solid #2b3344; background: #121622; color: #f5f7fb; }}
    #canvas {{ width: 100vw; height: calc(100vh - 74px); display: block; }}
    .legend {{ font-size: 12px; color: #9ca8be; }}
  </style>
</head>
<body>
  <header>
    <div>
      <strong>BrainGraph</strong>
      <div class="legend">Static graph viewer generated locally</div>
    </div>
    <input id="filter" placeholder="Filter nodes by file or symbol">
  </header>
  <canvas id="canvas"></canvas>
  <script>
    const data = {json.dumps(data)};
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const filter = document.getElementById('filter');
    const palette = {{ file: '#55f6a5', function: '#20e3ff', class: '#ffc857', api: '#ff4fa3', component: '#b084ff', default: '#94a3b8' }};
    const nodes = data.nodes.map((node, index) => ({{
      ...node,
      x: (index % 24) * 80 + 80,
      y: Math.floor(index / 24) * 64 + 80,
      vx: 0,
      vy: 0
    }}));
    const nodeMap = new Map(nodes.map(node => [node.id, node]));
    const edges = data.edges.filter(edge => nodeMap.has(edge.source) && nodeMap.has(edge.target));
    function resize() {{
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight - 74;
    }}
    function step() {{
      const q = filter.value.trim().toLowerCase();
      for (const node of nodes) {{
        node.vx *= 0.85;
        node.vy *= 0.85;
      }}
      for (const edge of edges) {{
        const a = nodeMap.get(edge.source);
        const b = nodeMap.get(edge.target);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(28, Math.hypot(dx, dy));
        const force = (dist - 70) * 0.0007;
        a.vx += dx * force;
        a.vy += dy * force;
        b.vx -= dx * force;
        b.vy -= dy * force;
      }}
      for (let i = 0; i < nodes.length; i++) {{
        for (let j = i + 1; j < nodes.length; j++) {{
          const a = nodes[i];
          const b = nodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.max(1, Math.hypot(dx, dy));
          const repel = 120 / (dist * dist);
          a.vx -= dx * repel * 0.001;
          a.vy -= dy * repel * 0.001;
          b.vx += dx * repel * 0.001;
          b.vy += dy * repel * 0.001;
        }}
      }}
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const edge of edges) {{
        const a = nodeMap.get(edge.source);
        const b = nodeMap.get(edge.target);
        const visible = !q || a.label.toLowerCase().includes(q) || b.label.toLowerCase().includes(q);
        if (!visible) continue;
        ctx.strokeStyle = 'rgba(255,255,255,0.12)';
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }}
      for (const node of nodes) {{
        node.x = Math.max(18, Math.min(canvas.width - 18, node.x + node.vx));
        node.y = Math.max(18, Math.min(canvas.height - 18, node.y + node.vy));
        const visible = !q || node.label.toLowerCase().includes(q) || node.type.toLowerCase().includes(q);
        if (!visible) continue;
        ctx.fillStyle = palette[node.type] || palette.default;
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.type === 'file' ? 6 : 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#f5f7fb';
        ctx.font = '11px Inter, Arial, sans-serif';
        ctx.fillText(node.label.slice(0, 54), node.x + 8, node.y - 8);
      }}
      requestAnimationFrame(step);
    }}
    resize();
    window.addEventListener('resize', resize);
    step();
  </script>
</body>
</html>"""
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def shortest_path(self, source_query: str, target_query: str) -> list[str]:
        graph = self.build()
        simple = nx.Graph()
        for node, attrs in graph.nodes(data=True):
            simple.add_node(node, **attrs)
        for source, target, attrs in graph.edges(data=True):
            simple.add_edge(source, target, **attrs)
        source = self._resolve_node(simple, source_query)
        target = self._resolve_node(simple, target_query)
        path = nx.shortest_path(simple, source=source, target=target)
        return [str(simple.nodes[node].get("label", node)) for node in path]

    def _resolve_node(self, graph: nx.Graph, query: str) -> str:
        needle = query.lower()
        exact = [node for node, attrs in graph.nodes(data=True) if str(attrs.get("label", "")).lower() == needle]
        if exact:
            return exact[0]
        partial = [
            node
            for node, attrs in graph.nodes(data=True)
            if needle in str(attrs.get("label", "")).lower() or needle in str(node).lower()
        ]
        if partial:
            return partial[0]
        raise ValueError(f"No graph node found for '{query}'.")

    def circular_imports(self) -> list[list[str]]:
        graph = nx.DiGraph()
        for relation in self.session.scalars(
            select(Relation).where(
                Relation.project_id == self.project_id,
                Relation.relation_type == "depends_on",
                Relation.source_type == "file",
                Relation.target_type == "file",
            )
        ):
            graph.add_edge(relation.source_key, relation.target_key)
        return list(nx.simple_cycles(graph))
