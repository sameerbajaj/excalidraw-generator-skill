from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from render_excalidraw import render
from serve_editor import serve


WORKSPACE_FILE = ".excalidraw-workspace.json"
MANIFEST_FILE = "manifest.json"
WORKSPACE_DIRS = ("inputs", "diagrams", "exports")


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


def source_markdown(title: str, text: str, diagram_rel: str) -> str:
    return (
        f"# {title}\n\n"
        f"- Diagram: `{diagram_rel}`\n"
        f"- Captured: `{now_iso()}`\n\n"
        "## Source Text\n\n"
        f"{text.strip()}\n"
    )


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


def create_diagram(args: argparse.Namespace) -> dict:
    workspace = args.workspace.resolve()
    init_workspace(workspace)
    title = args.title.strip()
    if not title:
        raise SystemExit("--title is required")

    source_text = read_source(args)
    slug = slugify(args.slug or title)
    input_path = unique_path(workspace / "inputs" / f"{slug}.md")
    diagram_path = unique_path(workspace / "diagrams" / f"{slug}.excalidraw")

    input_path.write_text(source_markdown(title, source_text, rel(diagram_path, workspace)), encoding="utf-8")
    if not args.no_starter:
        diagram_path.write_text(json.dumps(starter_excalidraw(title, source_text), indent=2) + "\n", encoding="utf-8")

    record = {
        "title": title,
        "slug": diagram_path.stem,
        "input": rel(input_path, workspace),
        "diagram": rel(diagram_path, workspace),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "starter-created" if not args.no_starter else "input-captured",
    }
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

    args = parser.parse_args()

    if args.command == "init":
        marker = init_workspace(args.workspace)
        print_json({"workspace": str(args.workspace.resolve()), "marker": marker})
    elif args.command == "new":
        print_json(create_diagram(args))
    elif args.command == "list":
        init_workspace(args.workspace)
        print_json(load_manifest(args.workspace.resolve()))
    elif args.command == "render-all":
        print_json(render_all(args.workspace, args.scale, args.width))
    elif args.command == "serve":
        init_workspace(args.workspace)
        serve(args.workspace, host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
