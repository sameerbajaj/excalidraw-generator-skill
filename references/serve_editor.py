from __future__ import annotations

import argparse
import html
import http.server
import json
import socket
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

from render_excalidraw import render, validate_excalidraw, write_editor_html


SKIP_DIRS = {
    ".cache",
    ".git",
    ".tempmediaStorage",
    ".venv",
    "__pycache__",
    "node_modules",
    "scratch",
}


TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Excalidraw Diagram Workspace</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #f8fafc;
      color: #0f172a;
      margin: 0;
      padding: 0;
    }
    header {
      background: #1e3a8a;
      color: white;
      padding: 20px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 24px;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    header h1 {
      margin: 0;
      font-size: 22px;
      font-weight: 800;
    }
    header p {
      margin: 4px 0 0 0;
      font-size: 13px;
      opacity: 0.84;
    }
    main {
      padding: 32px 40px 48px;
      max-width: 1280px;
      margin: 0 auto;
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 24px;
      color: #475569;
      font-size: 13px;
    }
    .workspace-path {
      background: #e2e8f0;
      color: #0f172a;
      border-radius: 6px;
      padding: 6px 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      overflow-wrap: anywhere;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 24px;
    }
    .card {
      background: white;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
      border: 1px solid #e2e8f0;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .preview-container {
      height: 190px;
      background: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      border-bottom: 1px solid #e2e8f0;
      position: relative;
    }
    .preview-container img {
      max-width: 96%;
      max-height: 96%;
      object-fit: contain;
    }
    .preview-placeholder {
      color: #64748b;
      font-size: 13px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      text-align: center;
      padding: 24px;
    }
    .card-content {
      padding: 18px;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .card-title {
      font-size: 16px;
      font-weight: 700;
      margin: 0 0 8px 0;
      color: #0f172a;
      overflow-wrap: anywhere;
    }
    .card-meta {
      font-size: 11px;
      color: #64748b;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .card-meta code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .render-controls {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      align-items: end;
    }
    label {
      display: flex;
      flex-direction: column;
      gap: 4px;
      color: #475569;
      font-size: 11px;
      font-weight: 600;
    }
    input,
    select {
      width: 100%;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 7px 8px;
      color: #0f172a;
      background: #ffffff;
      font: inherit;
      font-size: 13px;
    }
    .card-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .btn {
      border-radius: 6px;
      text-align: center;
      text-decoration: none;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s, opacity 0.2s;
      border: 1px solid transparent;
      padding: 8px 10px;
      min-height: 36px;
    }
    .btn-primary {
      background: #2563eb;
      color: white;
    }
    .btn-primary:hover { background: #1d4ed8; }
    .btn-secondary {
      background: #f1f5f9;
      color: #334155;
      border-color: #cbd5e1;
    }
    .btn-secondary:hover { background: #e2e8f0; }
    .btn-danger {
      background: #fee2e2;
      color: #b91c1c;
      border-color: #fca5a5;
    }
    .btn-danger:hover { background: #fecaca; }
    .btn[disabled] {
      cursor: not-allowed;
      opacity: 0.55;
    }
    .empty-state {
      text-align: center;
      padding: 60px;
      background: white;
      border-radius: 8px;
      border: 2px dashed #cbd5e1;
      color: #64748b;
    }
    .status-line {
      min-height: 18px;
      color: #475569;
      font-size: 12px;
    }
  </style>
  <script>
    async function postJSON(url, payload) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || "Request failed");
      }
      return data;
    }

    async function renderDiagram(path) {
      const card = document.querySelector(`[data-path="${CSS.escape(path)}"]`);
      const status = card.querySelector(".status-line");
      const button = card.querySelector("[data-action='render']");
      const scale = Number(card.querySelector("[data-field='scale']").value);
      const width = Number(card.querySelector("[data-field='width']").value);
      button.disabled = true;
      status.textContent = "Rendering preview...";
      try {
        await postJSON("/api/render", { path, scale, width });
        status.textContent = "Preview refreshed.";
        window.location.reload();
      } catch (err) {
        status.textContent = `Render failed: ${err.message}`;
        button.disabled = false;
      }
    }

    async function deleteDiagram(path) {
      if (!confirm(`Delete "${path}" and its PNG/editor companions? This cannot be undone.`)) {
        return;
      }
      try {
        await postJSON("/api/delete", { path });
        window.location.reload();
      } catch (err) {
        alert(`Delete failed: ${err.message}`);
      }
    }
  </script>
</head>
<body>
  <header>
    <div>
      <h1>Excalidraw Diagram Workspace</h1>
      <p>Store, render, edit, and export strategy diagrams from one local workspace.</p>
    </div>
    <div style="font-size: 12px; opacity: 0.86; text-align: right;">
      Status: <strong>Online</strong><br/>
      Context: <strong>Local Workspace</strong>
    </div>
  </header>
  <main>
    <div class="toolbar">
      <div>Workspace</div>
      <div class="workspace-path">[WORKSPACE_PATH]</div>
    </div>
    [CONTENT_HERE]
  </main>
</body>
</html>
"""


def should_skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return any(part in SKIP_DIRS for part in rel_parts)


def scan_diagrams(directory: Path) -> list[Path]:
    excalidraw_files: list[Path] = []
    for path in directory.glob("**/*.excalidraw"):
        if should_skip(path, directory):
            continue
        excalidraw_files.append(path)
    excalidraw_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return excalidraw_files


def prepare_editor(path: Path) -> tuple[bool, str | None]:
    editor_path = path.with_name(f"{path.name}_editor.html")
    if editor_path.exists() and editor_path.stat().st_mtime >= path.stat().st_mtime:
        return True, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        write_editor_html(path, data)
        return True, None
    except Exception as exc:
        return False, str(exc)


def href_for(rel_path: Path) -> str:
    return urllib.parse.quote(rel_path.as_posix())


def generate_dashboard(directory: Path, auto_prepare: bool = True) -> str:
    excalidraw_files = scan_diagrams(directory)

    if not excalidraw_files:
        content = """
        <div class="empty-state">
          <h2>No Excalidraw diagrams found in this workspace</h2>
          <p>Create a diagram through the skill workflow, then refresh this page.</p>
        </div>
        """
    else:
        cards = []
        for path in excalidraw_files:
            rel_path = path.relative_to(directory)
            rel_posix = rel_path.as_posix()
            rel_json = json.dumps(rel_posix)
            escaped_rel = html.escape(rel_posix)
            png_path = rel_path.with_suffix(".png")
            editor_path = rel_path.with_name(f"{rel_path.name}_editor.html")

            editor_error = None
            if auto_prepare:
                has_editor, editor_error = prepare_editor(path)
            else:
                has_editor = (directory / editor_path).exists()

            has_png = (directory / png_path).exists()
            mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
            title = html.escape(path.stem.replace("_", " ").replace("-", " ").title())

            if has_png:
                preview_html = f'<img src="{href_for(png_path)}" alt="{title} preview" />'
            else:
                preview_html = """
                <div class="preview-placeholder">
                  <strong>Preview not rendered</strong>
                  <span>Use Refresh Preview below.</span>
                </div>
                """

            if has_editor:
                editor_btn = f'<a class="btn btn-primary" href="{href_for(editor_path)}">Open Editor</a>'
            else:
                reason = html.escape(editor_error or "Editor unavailable")
                editor_btn = f'<button class="btn btn-primary" disabled title="{reason}">Editor Error</button>'

            cards.append(f"""
            <div class="card" data-path="{escaped_rel}">
              <div class="preview-container">
                {preview_html}
              </div>
              <div class="card-content">
                <div>
                  <h3 class="card-title">{title}</h3>
                  <div class="card-meta">
                    <strong>Path:</strong> <code>{escaped_rel}</code><br/>
                    <strong>Last modified:</strong> {mtime}
                  </div>
                </div>
                <div class="render-controls">
                  <label>
                    Scale
                    <select data-field="scale">
                      <option value="1">1x</option>
                      <option value="2" selected>2x</option>
                      <option value="3">3x</option>
                      <option value="4">4x</option>
                    </select>
                  </label>
                  <label>
                    Max width
                    <input data-field="width" type="number" min="640" max="4096" step="160" value="1920" />
                  </label>
                </div>
                <div class="card-actions">
                  {editor_btn}
                  <button class="btn btn-secondary" data-action="render" onclick='renderDiagram({rel_json})'>Refresh Preview</button>
                  <a class="btn btn-secondary" href="{href_for(rel_path)}" download>Download JSON</a>
                  <button class="btn btn-danger" onclick='deleteDiagram({rel_json})'>Delete</button>
                </div>
                <div class="status-line"></div>
              </div>
            </div>
            """)
        content = f'<div class="grid">{"".join(cards)}</div>'

    return (
        TEMPLATE
        .replace("[WORKSPACE_PATH]", html.escape(str(directory)))
        .replace("[CONTENT_HERE]", content)
    )


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


def resolve_workspace_path(directory: Path, rel_path: str) -> Path:
    target = (directory / rel_path).resolve()
    root = directory.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path escapes workspace")
    return target


def read_json_body(handler: http.server.BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def write_json(handler: http.server.BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    handler.send_response(status)
    handler.send_header("Content-type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode("utf-8"))


def write_diagram(path: Path, data: dict) -> None:
    errors = validate_excalidraw(data)
    if errors:
        raise ValueError("; ".join(errors))
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def clamp_int(value: object, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def serve(
    target_path: Path,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool = True,
) -> None:
    target_path = target_path.resolve()
    if target_path.is_file():
        directory = target_path.parent
        filename = target_path.name
        single_file_mode = True
    else:
        directory = target_path
        filename = "index.html"
        single_file_mode = False
    directory.mkdir(parents=True, exist_ok=True)

    selected_port = port if port is not None else get_free_port()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def do_GET(self):
            if not single_file_mode and self.path in ["", "/", "/index.html"]:
                try:
                    html_content = generate_dashboard(directory)
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(html_content.encode("utf-8"))
                except Exception as exc:
                    self.send_error(500, f"Error generating dashboard: {exc}")
            else:
                super().do_GET()

        def do_HEAD(self):
            if not single_file_mode and self.path in ["", "/", "/index.html"]:
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
            else:
                super().do_HEAD()

        def do_POST(self):
            if single_file_mode:
                write_json(self, 404, {"success": False, "error": "API unavailable in single-file mode"})
                return
            try:
                request = read_json_body(self)
                rel_path_str = request.get("path")
                if not rel_path_str:
                    write_json(self, 400, {"success": False, "error": "Missing path parameter"})
                    return

                diagram_path = resolve_workspace_path(directory, str(rel_path_str))
                if diagram_path.suffix != ".excalidraw":
                    write_json(self, 400, {"success": False, "error": "Path is not an .excalidraw file"})
                    return

                if self.path == "/api/save":
                    data = request.get("data")
                    if not isinstance(data, dict):
                        write_json(self, 400, {"success": False, "error": "Missing diagram data"})
                        return
                    write_diagram(diagram_path, data)
                    write_json(self, 200, {"success": True})
                    return

                if self.path == "/api/render":
                    if not diagram_path.exists():
                        write_json(self, 404, {"success": False, "error": "Diagram file not found"})
                        return
                    scale = clamp_int(request.get("scale"), 2, 1, 4)
                    width = clamp_int(request.get("width"), 1920, 640, 4096)
                    png_path = render(diagram_path, scale=scale, max_width=width)
                    rel_png = png_path.relative_to(directory).as_posix()
                    write_json(self, 200, {"success": True, "png": rel_png})
                    return

                if self.path == "/api/delete":
                    if not diagram_path.exists():
                        write_json(self, 404, {"success": False, "error": "Diagram file not found"})
                        return
                    diagram_path.unlink()
                    for companion in [
                        diagram_path.with_suffix(".png"),
                        diagram_path.with_name(f"{diagram_path.name}_editor.html"),
                    ]:
                        if companion.exists():
                            companion.unlink()
                    write_json(self, 200, {"success": True})
                    return

                write_json(self, 404, {"success": False, "error": "Endpoint not found"})
            except Exception as exc:
                write_json(self, 500, {"success": False, "error": str(exc)})

    class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = ThreadingServer((host, selected_port), Handler)
    url_host = "localhost" if host in {"", "0.0.0.0", "127.0.0.1"} else host
    url = f"http://{url_host}:{selected_port}/{urllib.parse.quote(filename)}"

    print(f"Starting server at http://{url_host}:{selected_port} serving {directory}")

    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    if open_browser:
        print(f"Opening browser at {url}...")
        webbrowser.open(url)
    else:
        print(f"Dashboard URL: {url}")

    print("Press Ctrl+C to stop the server.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server.")
        try:
            server.shutdown()
        except KeyboardInterrupt:
            pass
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve an Excalidraw diagram dashboard/editor")
    parser.add_argument("target", nargs="?", default=".", type=Path, help="Workspace directory or a single HTML/file target")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default: choose a free port)")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    args = parser.parse_args()

    serve(args.target, host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
