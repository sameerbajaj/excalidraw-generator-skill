"""Render Excalidraw JSON to PNG using Playwright + headless Chromium.

Usage:
    cd /path/to/excalidraw-generator-skill/references
    uv run python render_excalidraw.py <path-to-file.excalidraw> [--output path.png] [--scale 2] [--width 1920]

First-time setup:
    cd /path/to/excalidraw-generator-skill/references
    uv sync
    uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import urllib.request
from pathlib import Path

EXCALIDRAW_VERSION = "0.18.0"
EXCALIDRAW_ASSET_BASE = f"https://cdn.jsdelivr.net/npm/@excalidraw/excalidraw@{EXCALIDRAW_VERSION}/dist/prod/"
EXCALIDRAW_CSS_URL = f"{EXCALIDRAW_ASSET_BASE}index.min.css"
EXCALIDRAW_MODULE_URL = (
    f"https://esm.sh/@excalidraw/excalidraw@{EXCALIDRAW_VERSION}"
    "?external=react,react-dom&bundle-deps"
)
REACT_URL = "https://esm.sh/react@18"
REACT_JSX_URL = "https://esm.sh/react@18/jsx-runtime"
REACT_DOM_URL = "https://esm.sh/react-dom@18"
REACT_DOM_CLIENT_URL = "https://esm.sh/react-dom@18/client"

_EDITOR_CSS_CACHE: str | None = None


class RenderError(RuntimeError):
    """Raised when an Excalidraw file cannot be rendered."""


def validate_excalidraw(data: dict) -> list[str]:
    """Validate Excalidraw JSON structure. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    if data.get("type") != "excalidraw":
        errors.append(f"Expected type 'excalidraw', got '{data.get('type')}'")

    if "elements" not in data:
        errors.append("Missing 'elements' array")
    elif not isinstance(data["elements"], list):
        errors.append("'elements' must be an array")
    elif len(data["elements"]) == 0:
        errors.append("'elements' array is empty — nothing to render")

    return errors


def compute_bounding_box(elements: list[dict]) -> tuple[float, float, float, float]:
    """Compute bounding box (min_x, min_y, max_x, max_y) across all elements."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        if el.get("isDeleted"):
            continue
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)

        # For arrows/lines, points array defines the shape relative to x,y
        if el.get("type") in ("arrow", "line") and "points" in el:
            for px, py in el["points"]:
                min_x = min(min_x, x + px)
                min_y = min(min_y, y + py)
                max_x = max(max_x, x + px)
                max_y = max(max_y, y + py)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + abs(w))
            max_y = max(max_y, y + abs(h))

    if min_x == float("inf"):
        return (0, 0, 800, 600)

    return (min_x, min_y, max_x, max_y)


def load_editor_css() -> str:
    """Load Excalidraw CSS once and inline it so the editor cannot render unstyled."""
    global _EDITOR_CSS_CACHE
    if _EDITOR_CSS_CACHE is not None:
        return _EDITOR_CSS_CACHE

    try:
        with urllib.request.urlopen(EXCALIDRAW_CSS_URL, timeout=2) as response:
            css = response.read().decode("utf-8")
        if ".excalidraw" not in css:
            raise RenderError("Downloaded Excalidraw CSS did not contain expected rules")
        css = (
            css
            .replace("url(./", f"url({EXCALIDRAW_ASSET_BASE}")
            .replace('url("./', f'url("{EXCALIDRAW_ASSET_BASE}')
            .replace("url('./", f"url('{EXCALIDRAW_ASSET_BASE}")
        )
        _EDITOR_CSS_CACHE = css.replace("</style", "<\\/style")
    except Exception:
        # Keep a fallback instead of failing render/editor generation entirely.
        _EDITOR_CSS_CACHE = f'@import url("{EXCALIDRAW_CSS_URL}");'
    return _EDITOR_CSS_CACHE


def write_editor_html(excalidraw_path: Path, data: dict) -> Path:
    """Generate a companion interactive editor HTML file for the diagram."""
    editor_path = excalidraw_path.with_name(f"{excalidraw_path.name}_editor.html")
    safe_filename = html.escape(excalidraw_path.name)
    editor_css = load_editor_css()

    # Excalidraw template HTML string
    template = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Excalidraw Live Editor - {filename}</title>
  <style>
    body { margin: 0; padding: 0; overflow: hidden; }
    #app { height: 100vh; display: flex; flex-direction: column; }
    {editor_css}
  </style>
  <script>
    window.EXCALIDRAW_ASSET_PATH = "{asset_base}";
  </script>
  <script type="importmap">
    {
      "imports": {
        "react": "{react_url}",
        "react/jsx-runtime": "{react_jsx_url}",
        "react-dom": "{react_dom_url}",
        "react-dom/client": "{react_dom_client_url}"
      }
    }
  </script>
</head>
<body>
  <div id="app"></div>
  <script type="module">
    import React, { useState, useRef } from "react";
    import ReactDOM from "react-dom/client";
    import { Excalidraw } from "{excalidraw_module_url}";

    const initialData = {json_data};
    const sourcePath = decodeURIComponent(window.location.pathname.replace(/^\\//, "").replace(/_editor\\.html$/, ""));
    const serverSaveAvailable = window.location.protocol.startsWith("http") && sourcePath.endsWith(".excalidraw");

    function App() {
      const [fileBound, setFileBound] = useState(false);
      const [fileName, setFileName] = useState("");
      const [saveStatus, setSaveStatus] = useState(serverSaveAvailable ? "Workspace autosave ready" : "Disconnected");
      const fileHandleRef = useRef(null);
      const excalidrawAPIRef = useRef(null);
      const didReceiveInitialChangeRef = useRef(false);

      const handleBind = async () => {
        if (!window.showOpenFilePicker) {
          alert("This browser does not support direct local-file linking. Open through the dashboard for server autosave.");
          return;
        }
        try {
          const [handle] = await window.showOpenFilePicker({
            types: [{
              description: 'Excalidraw Files',
              accept: { 'application/json': ['.excalidraw', '.json'] }
            }],
            multiple: false
          });
          fileHandleRef.current = handle;
          setFileName(handle.name);
          setFileBound(true);

          // Sync initial file content to editor
          const file = await handle.getFile();
          const text = await file.text();
          const fileData = JSON.parse(text);
          if (excalidrawAPIRef.current) {
            excalidrawAPIRef.current.updateScene({
              elements: fileData.elements || [],
              appState: fileData.appState || {},
              files: fileData.files || {}
            });
          }
          setSaveStatus(`Linked local file: ${handle.name}`);
        } catch (err) {
          console.error("Binding failed:", err);
          setSaveStatus("Link failed");
        }
      };

      const buildDocument = (elements, appState, files) => ({
        type: "excalidraw",
        version: 2,
        source: "https://excalidraw.com",
        elements: elements.filter(el => !el.isDeleted),
        appState: {
          viewBackgroundColor: appState.viewBackgroundColor || "#ffffff",
          gridSize: appState.gridSize || 20
        },
        files: files || {}
      });

      const timerRef = useRef(null);
      const handleOnChange = (elements, appState, files) => {
        if (!didReceiveInitialChangeRef.current) {
          didReceiveInitialChangeRef.current = true;
          return;
        }
        if (!serverSaveAvailable && !fileHandleRef.current) return;
        
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(async () => {
          try {
            setSaveStatus("Saving...");
            const documentData = buildDocument(elements, appState, files);
            if (serverSaveAvailable) {
              const response = await fetch("/api/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: sourcePath, data: documentData })
              });
              const result = await response.json();
              if (!response.ok || !result.success) {
                throw new Error(result.error || "Server save failed");
              }
              setSaveStatus("Saved to workspace");
            } else {
              const writable = await fileHandleRef.current.createWritable();
              await writable.write(JSON.stringify(documentData, null, 2));
              await writable.close();
              setSaveStatus(`Saved to ${fileName || "linked file"}`);
            }
          } catch (err) {
            console.error("Auto-save failed:", err);
            setSaveStatus(`Save failed: ${err.message}`);
          }
        }, 800);
      };

      return React.createElement("div", { style: { display: "flex", flexDirection: "column", height: "100vh" } },
        React.createElement("header", {
          style: {
            padding: "8px 16px",
            background: "#1e3a5f",
            color: "white",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
          }
        },
          React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "16px" } },
            React.createElement("a", {
              href: "/",
              style: {
                background: "#3b82f6",
                color: "white",
                textDecoration: "none",
                padding: "6px 12px",
                borderRadius: "6px",
                fontWeight: "600",
                fontSize: "12px",
                display: "inline-flex",
                alignItems: "center"
              }
            }, "🏠 Dashboard"),
            React.createElement("div", null,
              React.createElement("h1", { style: { fontSize: "16px", margin: 0, fontWeight: "bold" } }, "Excalidraw Live Editor"),
              React.createElement("div", { style: { fontSize: "11px", opacity: 0.8 } }, "Dashboard sessions autosave to the workspace. Link Local File is only a fallback.")
            )
          ),
          React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "12px" } },
            React.createElement("span", {
              style: {
                background: serverSaveAvailable || fileBound ? "#10b981" : "#ef4444",
                padding: "4px 8px",
                borderRadius: "4px",
                fontSize: "12px",
                fontWeight: "bold",
                maxWidth: "360px",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap"
              }
            }, saveStatus),
            React.createElement("button", {
              onClick: handleBind,
              style: {
                background: "white",
                color: "#1e3a5f",
                border: "none",
                padding: "6px 12px",
                borderRadius: "4px",
                fontWeight: "bold",
                cursor: "pointer",
                fontFamily: "inherit",
                fontSize: "12px"
              }
            }, "🔗 Link Local File")
          )
        ),
        React.createElement("div", { style: { flex: 1, position: "relative" } },
          React.createElement(Excalidraw, {
            excalidrawAPI: (api) => { excalidrawAPIRef.current = api; },
            initialData: initialData,
            onChange: (elements, appState, files) => handleOnChange(elements, appState, files)
          })
        )
      );
    }

    const root = ReactDOM.createRoot(document.getElementById("app"));
    root.render(React.createElement(App));
  </script>
</body>
</html>"""
    
    # Strip deleted elements
    clean_data = {
        "type": data.get("type", "excalidraw"),
        "version": data.get("version", 2),
        "source": data.get("source", "https://excalidraw.com"),
        "elements": [el for el in data.get("elements", []) if not el.get("isDeleted")],
        "appState": data.get("appState", {}),
        "files": data.get("files", {})
    }
    
    html_content = (
        template
        .replace("{filename}", safe_filename)
        .replace("{editor_css}", editor_css)
        .replace("{asset_base}", EXCALIDRAW_ASSET_BASE)
        .replace("{react_url}", REACT_URL)
        .replace("{react_jsx_url}", REACT_JSX_URL)
        .replace("{react_dom_url}", REACT_DOM_URL)
        .replace("{react_dom_client_url}", REACT_DOM_CLIENT_URL)
        .replace("{excalidraw_module_url}", EXCALIDRAW_MODULE_URL)
        .replace("{json_data}", json.dumps(clean_data, indent=2))
    )
    editor_path.write_text(html_content, encoding="utf-8")
    return editor_path


def render(
    excalidraw_path: Path,
    output_path: Path | None = None,
    scale: int = 2,
    max_width: int = 1920,
) -> Path:
    """Render an .excalidraw file to PNG. Returns the output PNG path."""
    # Import playwright here so validation errors show before import errors
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RenderError(
            "playwright not installed. "
            f"Run: cd {Path(__file__).resolve().parent} && uv sync && uv run playwright install chromium"
        ) from exc

    # Read and validate
    raw = excalidraw_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RenderError(f"Invalid JSON in {excalidraw_path}: {e}") from e

    errors = validate_excalidraw(data)
    if errors:
        joined = "; ".join(errors)
        raise RenderError(f"Invalid Excalidraw file: {joined}")

    # Generate the companion editor HTML file
    try:
        editor_file = write_editor_html(excalidraw_path, data)
        print(f"Companion live editor generated at: {editor_file}")
    except Exception as e:
        print(f"WARNING: Could not generate companion editor HTML: {e}", file=sys.stderr)

    # Compute viewport size from element bounding box
    elements = [e for e in data["elements"] if not e.get("isDeleted")]
    min_x, min_y, max_x, max_y = compute_bounding_box(elements)
    padding = 80
    diagram_w = max_x - min_x + padding * 2
    diagram_h = max_y - min_y + padding * 2

    # Cap viewport width, let height be natural
    vp_width = min(int(diagram_w), max_width)
    vp_height = max(int(diagram_h), 600)

    # Output path
    if output_path is None:
        output_path = excalidraw_path.with_suffix(".png")

    # Template path (same directory as this script)
    template_path = Path(__file__).parent / "render_template.html"
    if not template_path.exists():
        raise RenderError(f"Template not found at {template_path}")

    template_url = template_path.as_uri()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
                raise RenderError(
                    "Chromium not installed for Playwright. "
                    f"Run: cd {Path(__file__).resolve().parent} && uv run playwright install chromium"
                ) from e
            raise

        page = browser.new_page(
            viewport={"width": vp_width, "height": vp_height},
            device_scale_factor=scale,
        )

        # Load the template
        page.goto(template_url)

        # Wait for the ES module to load (imports from esm.sh)
        page.wait_for_function("window.__moduleReady === true", timeout=30000)

        # Inject the diagram data and render
        result = page.evaluate("data => window.renderDiagram(data)", data)

        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown render error") if result else "renderDiagram returned null"
            browser.close()
            raise RenderError(f"Render failed: {error_msg}")

        # Wait for render completion signal
        page.wait_for_function("window.__renderComplete === true", timeout=15000)

        # Screenshot the SVG element
        svg_el = page.query_selector("#root svg")
        if svg_el is None:
            browser.close()
            raise RenderError("No SVG element found after render")

        svg_el.screenshot(path=str(output_path))
        browser.close()

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Excalidraw JSON to PNG")
    parser.add_argument("input", type=Path, help="Path to .excalidraw JSON file")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output PNG path (default: same name with .png)")
    parser.add_argument("--scale", "-s", type=int, default=2, help="Device scale factor (default: 2)")
    parser.add_argument("--width", "-w", type=int, default=1920, help="Max viewport width (default: 1920)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        png_path = render(args.input, args.output, args.scale, args.width)
    except RenderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(str(png_path))


if __name__ == "__main__":
    main()
