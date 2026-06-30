from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from render_excalidraw import render
from serve_editor import get_free_port, serve


WORKSPACE_FILE = ".excalidraw-workspace.json"
MANIFEST_FILE = "manifest.json"
WORKSPACE_DIRS = ("inputs", "diagrams", "exports")
SERVER_PID_FILE = ".server.pid"
SERVER_LOG_FILE = ".server.log"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "diagram"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for idx in range(2, 1000):
        candidate = parent / f"{stem}-{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique path for {path}")


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def init_workspace(workspace: Path) -> dict:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    for dirname in WORKSPACE_DIRS:
        (workspace / dirname).mkdir(exist_ok=True)

    marker_path = workspace / WORKSPACE_FILE
    if marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["updated_at"] = now_iso()
    else:
        marker = {
            "version": 1,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "dirs": {
                "inputs": "inputs",
                "diagrams": "diagrams",
                "exports": "exports",
            },
        }
    marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

    manifest_path = workspace / MANIFEST_FILE
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps({"version": 1, "diagrams": []}, indent=2) + "\n", encoding="utf-8")

    return marker


def load_manifest(workspace: Path) -> dict:
    manifest_path = workspace / MANIFEST_FILE
    if not manifest_path.exists():
        return {"version": 1, "diagrams": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def save_manifest(workspace: Path, manifest: dict) -> None:
    manifest_path = workspace / MANIFEST_FILE
    manifest["updated_at"] = now_iso()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def upsert_record(workspace: Path, record: dict) -> None:
    manifest = load_manifest(workspace)
    diagrams = manifest.setdefault("diagrams", [])
    diagrams[:] = [item for item in diagrams if item.get("diagram") != record["diagram"]]
    diagrams.insert(0, record)
    save_manifest(workspace, manifest)


def read_source(args: argparse.Namespace) -> str:
    sources = [bool(args.text), bool(args.source), bool(args.stdin)]
    if sum(sources) > 1:
        raise SystemExit("Use only one of --text, --source, or --stdin")
    if args.text:
        return args.text
    if args.source:
        return args.source.read_text(encoding="utf-8")
    if args.stdin:
        return sys.stdin.read()
    return ""


def source_markdown(title: str, text: str, diagram_rel: str, metadata: dict[str, str] | None = None) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Diagram: `{diagram_rel}`",
        f"- Captured: `{now_iso()}`",
    ]
    for key, value in (metadata or {}).items():
        if value:
            lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Source Text", "", text.strip(), ""])
    return "\n".join(lines)


def wrapped_excerpt(text: str, width: int = 72, max_lines: int = 12) -> str:
    clean = " ".join(text.strip().split())
    if not clean:
        clean = "No source text captured yet. Replace this starter with the requested diagram."
    lines = textwrap.wrap(clean, width=width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    return "\n".join(lines)


def text_element(
    element_id: str,
    x: int,
    y: int,
    width: int,
    text: str,
    font_size: int,
    color: str,
    seed: int,
) -> dict:
    line_count = max(1, text.count("\n") + 1)
    height = int(font_size * 1.25 * line_count)
    return {
        "type": "text",
        "id": element_id,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": seed,
        "version": 1,
        "versionNonce": seed + 1000,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "text": text,
        "fontSize": font_size,
        "fontFamily": 3,
        "textAlign": "left",
        "verticalAlign": "top",
        "containerId": None,
        "originalText": text,
        "lineHeight": 1.25,
    }


def line_element(element_id: str, x: int, y: int, width: int, seed: int) -> dict:
    return {
        "type": "line",
        "id": element_id,
        "x": x,
        "y": y,
        "width": width,
        "height": 0,
        "angle": 0,
        "strokeColor": "#1e3a5f",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": seed,
        "version": 1,
        "versionNonce": seed + 1000,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "points": [[0, 0], [width, 0]],
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": None,
        "endArrowhead": None,
    }


def starter_excalidraw(title: str, text: str) -> dict:
    excerpt = wrapped_excerpt(text)
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": [
            text_element("starter_title", 120, 90, 900, title, 32, "#1e40af", 10001),
            text_element(
                "starter_subtitle",
                120,
                142,
                860,
                "Source captured. Replace this starter canvas with the selected visual argument.",
                16,
                "#64748b",
                10002,
            ),
            line_element("starter_rule", 120, 188, 900, 10003),
            text_element("starter_source_label", 120, 230, 400, "Source excerpt", 20, "#3b82f6", 10004),
            text_element("starter_source", 120, 270, 860, excerpt, 16, "#374151", 10005),
        ],
        "appState": {
            "viewBackgroundColor": "#ffffff",
            "gridSize": 20,
        },
        "files": {},
    }


def create_diagram_from_text(
    workspace: Path,
    title: str,
    source_text: str,
    slug: str | None = None,
    no_starter: bool = False,
    metadata: dict[str, str] | None = None,
    extra_record: dict | None = None,
) -> dict:
    workspace = workspace.resolve()
    init_workspace(workspace)
    title = title.strip()
    if not title:
        raise ValueError("title is required")

    slug = slugify(slug or title)
    input_path = unique_path(workspace / "inputs" / f"{slug}.md")
    diagram_path = unique_path(workspace / "diagrams" / f"{slug}.excalidraw")

    input_path.write_text(
        source_markdown(title, source_text, rel(diagram_path, workspace), metadata=metadata),
        encoding="utf-8",
    )
    if not no_starter:
        diagram_path.write_text(json.dumps(starter_excalidraw(title, source_text), indent=2) + "\n", encoding="utf-8")

    record = {
        "title": title,
        "slug": diagram_path.stem,
        "input": rel(input_path, workspace),
        "diagram": rel(diagram_path, workspace),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "starter-created" if not no_starter else "input-captured",
    }
    if extra_record:
        record.update(extra_record)
    upsert_record(workspace, record)
    return {
        "workspace": str(workspace),
        "input_path": str(input_path),
        "diagram_path": str(diagram_path),
        "record": record,
        "next_steps": [
            "Design the diagram in the printed diagram_path.",
            "Render it with render_excalidraw.py or excalidraw_workspace.py render-all.",
            "Serve the workspace with excalidraw_workspace.py serve.",
        ],
    }


def create_diagram(args: argparse.Namespace) -> dict:
    return create_diagram_from_text(
        workspace=args.workspace,
        title=args.title,
        source_text=read_source(args),
        slug=args.slug,
        no_starter=args.no_starter,
    )


def parse_gdoc_url(url: str) -> tuple[str, str | None]:
    parsed = urllib.parse.urlparse(url)
    doc_match = re.search(r"/document/d/([^/]+)", parsed.path)
    if not doc_match:
        raise ValueError("Could not find a Google Doc document id in the URL")
    query = urllib.parse.parse_qs(parsed.query)
    tab_id = query.get("tab", [None])[0]
    return doc_match.group(1), tab_id


def run_gws_document_get(document_id: str) -> dict:
    params = {
        "documentId": document_id,
        "includeTabsContent": True,
        "fields": (
            "title,revisionId,"
            "tabs(tabProperties(tabId,title,index),"
            "documentTab(body(content(paragraph(elements(textRun(content)))))))"
        ),
    }
    command = ["gws", "docs", "documents", "get", "--params", json.dumps(params)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"gws document read failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gws returned non-JSON output: {result.stdout[:500]}") from exc


def extract_tab_text(document: dict, tab_id: str | None = None, tab_index: int | None = None) -> tuple[dict, str]:
    tabs = document.get("tabs") or []
    if not tabs:
        raise ValueError("The document response did not include tabs")

    target = None
    if tab_id:
        target = next((tab for tab in tabs if tab.get("tabProperties", {}).get("tabId") == tab_id), None)
        if target is None:
            raise ValueError(f"Tab id not found: {tab_id}")
    elif tab_index is not None:
        target = next((tab for tab in tabs if tab.get("tabProperties", {}).get("index") == tab_index), None)
        if target is None:
            raise ValueError(f"Tab index not found: {tab_index}")
    elif len(tabs) == 1:
        target = tabs[0]
    else:
        tab_list = ", ".join(
            f"{tab.get('tabProperties', {}).get('index')}:{tab.get('tabProperties', {}).get('tabId')}"
            for tab in tabs
        )
        raise ValueError(f"Multiple tabs found; provide --tab-id or a URL with ?tab=. Tabs: {tab_list}")

    parts: list[str] = []
    content = target.get("documentTab", {}).get("body", {}).get("content", [])
    for item in content:
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []):
            text_run = element.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return target, "".join(parts).strip() + "\n"


def create_from_gdoc(args: argparse.Namespace) -> dict:
    if args.url:
        document_id, url_tab_id = parse_gdoc_url(args.url)
        tab_id = args.tab_id or url_tab_id
    else:
        if not args.document_id:
            raise SystemExit("Provide --url or --document-id")
        document_id = args.document_id
        tab_id = args.tab_id

    document = run_gws_document_get(document_id)
    tab, text = extract_tab_text(document, tab_id=tab_id, tab_index=args.tab_index)
    props = tab.get("tabProperties", {})
    title = args.title or f"{document.get('title', 'Google Doc')} - {props.get('title', 'Tab')}"
    metadata = {
        "Document": document.get("title", ""),
        "Document ID": document_id,
        "Tab": f"{props.get('title', '')} ({props.get('tabId', '')})",
        "Revision": document.get("revisionId", ""),
    }
    extra_record = {
        "source_document_id": document_id,
        "source_tab_id": props.get("tabId", ""),
        "source_tab_title": props.get("title", ""),
        "source_revision_id": document.get("revisionId", ""),
        "source_char_count": len(text),
    }
    created = create_diagram_from_text(
        workspace=args.workspace,
        title=title,
        source_text=text,
        slug=args.slug,
        no_starter=args.no_starter,
        metadata=metadata,
        extra_record=extra_record,
    )
    created["source"] = {
        "document_id": document_id,
        "document_title": document.get("title"),
        "tab_id": props.get("tabId"),
        "tab_title": props.get("title"),
        "tab_index": props.get("index"),
        "chars": len(text),
    }

    if args.render and not args.no_starter:
        png_path = render(Path(created["diagram_path"]), scale=args.scale, max_width=args.width)
        png_rel = rel(png_path, args.workspace.resolve())
        render_updates = {"status": "rendered", "png": png_rel}
        created["png_path"] = str(png_path)
        created["record"].update(render_updates)
        update_record(args.workspace, created["record"]["diagram"], render_updates)

    if args.serve:
        created["server"] = serve_daemon(
            args.workspace,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )

    return created


def update_record(workspace: Path, diagram_rel: str, updates: dict) -> None:
    workspace = workspace.resolve()
    manifest = load_manifest(workspace)
    for item in manifest.setdefault("diagrams", []):
        if item.get("diagram") == diagram_rel:
            item.update(updates)
            item["updated_at"] = now_iso()
            break
    save_manifest(workspace, manifest)


def render_all(workspace: Path, scale: int, width: int) -> list[dict]:
    workspace = workspace.resolve()
    init_workspace(workspace)
    results = []
    for diagram_path in sorted((workspace / "diagrams").glob("*.excalidraw")):
        try:
            png_path = render(diagram_path, scale=scale, max_width=width)
            results.append({"diagram": str(diagram_path), "png": str(png_path), "success": True})
        except Exception as exc:
            results.append({"diagram": str(diagram_path), "success": False, "error": str(exc)})
    return results


def health_check(url: str, timeout_seconds: float = 5.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.2)
    return False


def server_state_paths(workspace: Path) -> tuple[Path, Path]:
    workspace = workspace.resolve()
    return workspace / SERVER_PID_FILE, workspace / SERVER_LOG_FILE


def serve_daemon(
    workspace: Path,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool = False,
) -> dict:
    workspace = workspace.resolve()
    init_workspace(workspace)
    selected_port = port if port is not None else get_free_port()
    pid_path, log_path = server_state_paths(workspace)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        str(workspace),
        "--host",
        host,
        "--port",
        str(selected_port),
        "--no-browser",
    ]
    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parent),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path.write_text(str(process.pid) + "\n", encoding="utf-8")
    url_host = "localhost" if host in {"", "0.0.0.0", "127.0.0.1"} else host
    url = f"http://{url_host}:{selected_port}/index.html"
    ok = health_check(url)
    if open_browser and ok:
        import webbrowser

        webbrowser.open(url)
    return {
        "pid": process.pid,
        "url": url,
        "healthy": ok,
        "log": str(log_path),
        "pid_file": str(pid_path),
    }


def stop_server(workspace: Path) -> dict:
    workspace = workspace.resolve()
    pid_path, _ = server_state_paths(workspace)
    if not pid_path.exists():
        return {"stopped": False, "reason": "no pid file"}
    pid = int(pid_path.read_text(encoding="utf-8").strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_path.unlink(missing_ok=True)
        return {"stopped": False, "reason": "process not running", "pid": pid}
    pid_path.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def doctor(workspace: Path | None = None) -> dict:
    checks = {
        "gws": bool(shutil.which("gws")),
        "uv": bool(shutil.which("uv")),
    }
    try:
        import playwright.sync_api  # noqa: F401

        checks["playwright_python"] = True
    except ImportError:
        checks["playwright_python"] = False
    if workspace is not None:
        try:
            init_workspace(workspace)
            probe = workspace.resolve() / ".write-test"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink()
            checks["workspace_writable"] = True
        except Exception:
            checks["workspace_writable"] = False
    return {"ok": all(checks.values()), "checks": checks}


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage an Excalidraw diagram workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the workspace directories and manifest")
    init_parser.add_argument("workspace", type=Path)

    new_parser = subparsers.add_parser("new", help="Capture source text and create a starter diagram")
    new_parser.add_argument("workspace", type=Path)
    new_parser.add_argument("--title", required=True)
    new_parser.add_argument("--slug", default=None)
    new_parser.add_argument("--text", default=None)
    new_parser.add_argument("--source", type=Path, default=None)
    new_parser.add_argument("--stdin", action="store_true")
    new_parser.add_argument("--no-starter", action="store_true")

    gdoc_parser = subparsers.add_parser("from-gdoc", help="Capture a Google Doc tab through gws")
    gdoc_parser.add_argument("workspace", type=Path)
    gdoc_source = gdoc_parser.add_mutually_exclusive_group(required=True)
    gdoc_source.add_argument("--url")
    gdoc_source.add_argument("--document-id")
    gdoc_parser.add_argument("--tab-id", default=None)
    gdoc_parser.add_argument("--tab-index", type=int, default=None)
    gdoc_parser.add_argument("--title", default=None)
    gdoc_parser.add_argument("--slug", default=None)
    gdoc_parser.add_argument("--no-starter", action="store_true")
    gdoc_parser.add_argument("--render", action="store_true")
    gdoc_parser.add_argument("--scale", type=int, default=2)
    gdoc_parser.add_argument("--width", type=int, default=1920)
    gdoc_parser.add_argument("--serve", action="store_true")
    gdoc_parser.add_argument("--host", default="127.0.0.1")
    gdoc_parser.add_argument("--port", type=int, default=None)
    gdoc_parser.add_argument("--no-browser", action="store_true")

    list_parser = subparsers.add_parser("list", help="Print the workspace manifest")
    list_parser.add_argument("workspace", type=Path)

    render_parser = subparsers.add_parser("render-all", help="Render every diagram in the workspace")
    render_parser.add_argument("workspace", type=Path)
    render_parser.add_argument("--scale", type=int, default=2)
    render_parser.add_argument("--width", type=int, default=1920)

    serve_parser = subparsers.add_parser("serve", help="Open the local dashboard/editor server")
    serve_parser.add_argument("workspace", type=Path)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--no-browser", action="store_true")
    serve_parser.add_argument("--daemon", action="store_true")

    stop_parser = subparsers.add_parser("stop-server", help="Stop a daemonized workspace server")
    stop_parser.add_argument("workspace", type=Path)

    doctor_parser = subparsers.add_parser("doctor", help="Check local dependencies")
    doctor_parser.add_argument("workspace", nargs="?", default=None, type=Path)

    args = parser.parse_args()

    if args.command == "init":
        marker = init_workspace(args.workspace)
        print_json({"workspace": str(args.workspace.resolve()), "marker": marker})
    elif args.command == "new":
        print_json(create_diagram(args))
    elif args.command == "from-gdoc":
        print_json(create_from_gdoc(args))
    elif args.command == "list":
        init_workspace(args.workspace)
        print_json(load_manifest(args.workspace.resolve()))
    elif args.command == "render-all":
        print_json(render_all(args.workspace, args.scale, args.width))
    elif args.command == "serve":
        init_workspace(args.workspace)
        if args.daemon:
            print_json(serve_daemon(args.workspace, host=args.host, port=args.port, open_browser=not args.no_browser))
        else:
            serve(args.workspace, host=args.host, port=args.port, open_browser=not args.no_browser)
    elif args.command == "stop-server":
        print_json(stop_server(args.workspace))
    elif args.command == "doctor":
        print_json(doctor(args.workspace))


if __name__ == "__main__":
    main()
