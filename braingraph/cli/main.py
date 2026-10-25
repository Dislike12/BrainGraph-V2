from __future__ import annotations

import json
import os
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from threading import Timer

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from braingraph import __version__
from braingraph.config import BrainGraphConfig
from braingraph.integrations import INTEGRATIONS, install_integration
from braingraph.service import BrainGraphService
from braingraph.watcher.watch import watch_project

app = typer.Typer(
    help="BrainGraph is a Graphify-style codebase graph memory tool for CLI and AI workflows.",
    invoke_without_command=True,
    no_args_is_help=False,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
console = Console()


def version_callback(value: bool) -> None:
    if not value:
        return
    console.print(__version__)
    raise typer.Exit()


def resolve_project(project: Path | None = None) -> Path:
    return (project or Path.cwd()).resolve()


def ensure_index(project: Path) -> BrainGraphService:
    svc = BrainGraphService(project)
    if not svc.config.db_path.exists():
        svc.init_project()
    return svc


def scan_project(project: Path, initialize: bool = False) -> dict[str, str | int | float]:
    started = time.perf_counter()
    service = BrainGraphService(project)
    result = service.init_project() if initialize else service.scan()
    elapsed = round(time.perf_counter() - started, 3)
    service.config.ensure_dirs()
    (service.config.output_dir / "dashboard.json").write_text(
        json.dumps({"scan_seconds": elapsed, "file_count": result["files"]}, indent=2),
        encoding="utf-8",
    )
    return {**result, "scan_seconds": elapsed}


def open_dashboard(project: Path, host: str, port: int, open_browser: bool = True) -> None:
    import uvicorn

    project_path = project.expanduser().resolve()
    load_dotenv(project_path / ".env", override=False)
    os.environ["BRAINGRAPH_PROJECT"] = str(project_path)
    url = f"http://{host}:{port}"
    console.print(f"[green]BrainGraph dashboard[/green] {url}")
    console.print(f"[dim]Project data: {project_path / '.braingraph'}[/dim]")
    if open_browser:
        browser_timer = Timer(1.0, webbrowser.open, args=(url,))
        browser_timer.daemon = True
        browser_timer.start()
    uvicorn.run("braingraph.web:app", host=host, port=port, reload=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed BrainGraph version and exit.",
        is_eager=True,
        callback=version_callback,
    ),
) -> None:
    """Run `braingraph scan .` from a repository to build its local index."""
    del version
    if ctx.invoked_subcommand is None:
        if not ctx.args:
            console.print(ctx.get_help())
            raise typer.Exit()
        project = resolve_project(Path(ctx.args[0]))
        result = scan_project(project, initialize=True)
        console.print(
            f"[green]BrainGraph indexed[/green] {result['files']} files into {result['output_dir']}"
        )
        open_dashboard(project, "127.0.0.1", 8000)


@app.command()
def install(project: Path | None = typer.Argument(None, exists=False, dir_okay=True, file_okay=False)) -> None:
    """Scan a repository and open its local BrainGraph dashboard."""
    path = resolve_project(project)
    result = scan_project(path, initialize=True)
    console.print(f"[green]Scanned[/green] {result['files']} files into {result['output_dir']}")
    open_dashboard(path, "127.0.0.1", 8000)


@app.command("init")
def init_command(project: Path | None = typer.Argument(None, exists=False, dir_okay=True, file_okay=False)) -> None:
    """Alias for install for users expecting `braingraph init`."""
    install(project)


@app.command("version")
def version_command() -> None:
    """Show the installed BrainGraph version."""
    console.print(__version__)


@app.command()
def update(project: Path | None = typer.Argument(None, exists=False, dir_okay=True, file_okay=False)) -> None:
    """Refresh graph, summaries, report, and memory."""
    path = resolve_project(project)
    result = scan_project(path)
    console.print(
        f"[green]Updated[/green] {path} -> files={result['files']} chunks={result['chunks']} diagnostics={result['diagnostics']}"
    )


@app.command()
def scan(
    project: Path | None = typer.Argument(None, exists=False, dir_okay=True, file_okay=False),
    host: str = typer.Option("127.0.0.1", help="Bind address for the local dashboard."),
    port: int = typer.Option(8000, min=1, max=65535, help="Dashboard HTTP port."),
    no_open: bool = typer.Option(False, "--no-open", help="Print the URL without opening a browser."),
) -> None:
    """Scan a repository from the terminal, then serve its local dashboard."""
    path = resolve_project(project)
    result = scan_project(path, initialize=True)
    console.print(
        f"[green]Scanned[/green] {result['files']} files, {result['chunks']} chunks, "
        f"{result['diagnostics']} diagnostics -> {result['output_dir']}"
    )
    open_dashboard(path, host, port, open_browser=not no_open)


@app.command()
def query(
    text: str,
    project: Path | None = typer.Option(None, "--project", "-p"),
    limit: int = typer.Option(8, min=1, max=30),
) -> None:
    """Query compact context from graph + memory."""
    result = ensure_index(resolve_project(project)).retrieve(text, limit)
    console.print(f"[cyan]Files[/cyan]: {', '.join(result['files']) or 'none'}")
    console.print(f"[cyan]Tokens[/cyan]: raw={result['raw_tokens']} compact={result['context_tokens']}")
    console.print()
    console.print(result["context"] or "No compact context found.")


@app.command()
def explain(
    text: str,
    project: Path | None = typer.Option(None, "--project", "-p"),
    limit: int = typer.Option(12, min=1, max=30),
) -> None:
    """Explain a system using BrainGraph context first."""
    result = ensure_index(resolve_project(project)).explain(text, limit)
    console.print(result["text"])


@app.command(name="path")
def path_command(
    source: str,
    target: str,
    project: Path | None = typer.Option(None, "--project", "-p"),
) -> None:
    """Find the shortest relationship path between modules or symbols."""
    route = ensure_index(resolve_project(project)).shortest_path(source, target)
    console.print(" -> ".join(route))


@app.command()
def stats(project: Path | None = typer.Option(None, "--project", "-p")) -> None:
    """Show scan and token optimization stats."""
    data = ensure_index(resolve_project(project)).stats()
    table = Table(title="BrainGraph Stats")
    table.add_column("Metric")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(key, str(value))
    console.print(table)


@app.command()
def graph(project: Path | None = typer.Option(None, "--project", "-p")) -> None:
    """Re-export graph.json and graph.html."""
    svc = ensure_index(resolve_project(project))
    svc.graph()
    html = svc.graph_html()
    console.print(f"[green]Exported[/green] graph.json and {html}")


@app.command()
def watch(
    project: Path | None = typer.Argument(None, exists=False, dir_okay=True, file_okay=False),
    seconds: float | None = typer.Option(
        None,
        "--seconds",
        min=0.1,
        help="Stop watching after this many seconds. Useful for smoke tests and CI.",
    ),
) -> None:
    """Watch a project and auto-refresh BrainGraph outputs."""
    path = resolve_project(project)
    console.print(f"[cyan]Watching[/cyan] {path}")
    watch_project(path, duration_seconds=seconds)


@app.command()
def doctor(project: Path | None = typer.Option(None, "--project", "-p")) -> None:
    """Show diagnostics like circular imports and duplicate files."""
    items = ensure_index(resolve_project(project)).diagnostics()
    if not items:
        console.print("[green]No issues found[/green]")
        return
    table = Table(title="BrainGraph Doctor")
    table.add_column("Severity")
    table.add_column("Code")
    table.add_column("File")
    table.add_column("Message")
    for item in items:
        table.add_row(item["severity"], item["code"], item.get("file_path") or "", item["message"])
    console.print(table)


@app.command()
def dashboard(
    project: Path | None = typer.Argument(None, exists=False, dir_okay=True, file_okay=False),
    host: str = typer.Option("127.0.0.1", help="Bind address for the local dashboard."),
    port: int = typer.Option(8000, min=1, max=65535, help="Dashboard HTTP port."),
    no_open: bool = typer.Option(False, "--no-open", help="Print the URL without opening a browser."),
) -> None:
    """Open the local dashboard for an already indexed repository."""
    path = resolve_project(project)
    if not BrainGraphConfig.load(path).db_path.is_file():
        console.print("[yellow]No index found. Run `braingraph scan .` first.[/yellow]")
        raise typer.Exit(code=1)
    open_dashboard(path, host, port, open_browser=not no_open)


@app.command()
def clear(
    project: Path | None = typer.Option(None, "--project", "-p"),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
) -> None:
    """Remove the project's .braingraph index and generated data."""
    path = BrainGraphConfig.load(resolve_project(project)).output_dir
    if not path.exists():
        console.print("[yellow]No .braingraph directory found[/yellow]")
        raise typer.Exit()
    if not yes and not typer.confirm(f"Delete {path}?"):
        raise typer.Abort()
    last_error: OSError | None = None
    for _attempt in range(3):
        try:
            shutil.rmtree(path)
            break
        except FileNotFoundError:
            break
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
    if path.exists():
        if last_error is not None:
            raise last_error
        raise typer.Exit(code=1)
    console.print(f"[green]Deleted[/green] {path}")


def _install_tool(tool: str, project: Path | None) -> None:
    repo_file = install_integration(resolve_project(project), tool)
    label = str(INTEGRATIONS[tool].get("label", tool))
    console.print(f"[green]{label} integration installed[/green] -> {repo_file}")


for tool_name, spec in INTEGRATIONS.items():
    label = str(spec.get("label", tool_name))
    subapp = typer.Typer(help=f"{label} integration commands.")

    @subapp.command("install")
    def install_tool(
        project: Path | None = typer.Argument(None, exists=False, dir_okay=True, file_okay=False),
        _tool: str = tool_name,
    ) -> None:
        _install_tool(_tool, project)

    for command_name in tuple(spec.get("commands", (tool_name,))):
        app.add_typer(subapp, name=command_name)


def run() -> None:
    commands = {
        "install",
        "init",
        "update",
        "scan",
        "query",
        "path",
        "explain",
        "version",
        "stats",
        "graph",
        "watch",
        "doctor",
        "dashboard",
        "clear",
        "--help",
        "-h",
        "--version",
    }
    for spec in INTEGRATIONS.values():
        commands.update(str(command) for command in tuple(spec.get("commands", ())))
    argv = sys.argv[1:]
    if argv and argv[0] not in commands and not argv[0].startswith("-"):
        project = resolve_project(Path(argv[0]))
        result = scan_project(project, initialize=True)
        console.print(
            f"[green]BrainGraph indexed[/green] {result['files']} files into {result['output_dir']}"
        )
        open_dashboard(project, "127.0.0.1", 8000)
        return
    app()


if __name__ == "__main__":
    run()
