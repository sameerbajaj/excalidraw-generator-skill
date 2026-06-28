"""Render Excalidraw JSON to PNG using Playwright + headless Chromium.

Usage:
    cd .claude/skills/excalidraw-diagram/references
    uv run python render_excalidraw.py <path-to-file.excalidraw> [--output path.png] [--scale 2] [--width 1920]

First-time setup:
    cd .claude/skills/excalidraw-diagram/references
    uv sync
    uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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


def write_editor_html(excalidraw_path: Path, data: dict) -> Path:
    """Generate a companion interactive editor HTML file for the diagram."""
    editor_path = excalidraw_path.with_name(f"{excalidraw_path.name}_editor.html")
    
    # Excalidraw template HTML string
    template = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Excalidraw Live Editor - {filename}</title>
  <style>
    body { margin: 0; padding: 0; }
    #app { height: 100vh; display: flex; flex-direction: column; }
  </style>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@excalidraw/excalidraw@0.18.0/dist/prod/index.min.css" />
  <script>
    window.EXCALIDRAW_ASSET_PATH = "https://cdn.jsdelivr.net/npm/@excalidraw/excalidraw@0.18.0/dist/prod/";
  </script>
  <script type="importmap">
    {
      "imports": {
        "react": "https://esm.sh/react@18",
        "react/jsx-runtime": "https://esm.sh/react@18/jsx-runtime",
        "react-dom": "https://esm.sh/react-dom@18",
        "react-dom/client": "https://esm.sh/react-dom@18/client"
      }
    }
  </script>
</head>
<body>
  <div id="app"></div>
  <script type="module">
    import React, { useState, useEffect, useRef } from "react";
    import ReactDOM from "react-dom/client";
    import { Excalidraw } from "https://esm.sh/@excalidraw/excalidraw@0.18.0?external=react,react-dom&bundle-deps";

    const initialData = {json_data};

    function App() {
      const [fileBound, setFileBound] = useState(false);
      const [fileName, setFileName] = useState("");
      const fileHandleRef = useRef(null);
      const [excalidrawAPI, setExcalidrawAPI] = useState(null);

      const handleBind = async () => {
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
          if (excalidrawAPI) {
            excalidrawAPI.updateScene({
              elements: fileData.elements || [],
              appState: fileData.appState || {},
              files: fileData.files || {}
            });
          }
        } catch (err) {
          console.error("Binding failed:", err);
        }
      };

      const timerRef = useRef(null);
      const handleOnChange = (elements, appState, files) => {
        if (!fileHandleRef.current) return;
        
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(async () => {
          try {
            const writable = await fileHandleRef.current.createWritable();
            const jsonContent = JSON.stringify({
              type: "excalidraw",
              version: 2,
              source: "https://excalidraw.com",
              elements: elements.filter(el => !el.isDeleted),
              appState: {
                viewBackgroundColor: appState.viewBackgroundColor || "#ffffff",
                gridSize: appState.gridSize || 20
              },
              files: files || {}
            }, null, 2);
            await writable.write(jsonContent);
            await writable.close();
            console.log("Auto-saved changes to disk!");
          } catch (err) {
            console.error("Auto-save failed:", err);
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
          React.createElement("div", null,
            React.createElement("h1", { style: { fontSize: "16px", margin: 0, fontWeight: "bold" } }, "Excalidraw Live Editor"),
            React.createElement("div", { style: { fontSize: "11px", opacity: 0.8 } }, "Double-click this HTML file, click 'Link Local File', and edit in real-time.")
          ),
          React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "12px" } },
            fileBound ? React.createElement("span", { style: { background: "#10b981", padding: "4px 8px", borderRadius: "4px", fontSize: "12px", fontWeight: "bold" } }, `Connected: ${fileName}`)
                      : React.createElement("span", { style: { background: "#ef4444", padding: "4px 8px", borderRadius: "4px", fontSize: "12px", fontWeight: "bold" } }, "Disconnected"),
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
            ref: (api) => setExcalidrawAPI(api),
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
    
    html_content = template.replace("{filename}", excalidraw_path.name).replace("{json_data}", json.dumps(clean_data, indent=2))
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
    except ImportError:
        print("ERROR: playwright not installed.", file=sys.stderr)
        print("Run: cd .claude/skills/excalidraw-diagram/references && uv sync && uv run playwright install chromium", file=sys.stderr)
        sys.exit(1)

    # Read and validate
    raw = excalidraw_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {excalidraw_path}: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate_excalidraw(data)
    if errors:
        print(f"ERROR: Invalid Excalidraw file:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

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
        print(f"ERROR: Template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    template_url = template_path.as_uri()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
                print("ERROR: Chromium not installed for Playwright.", file=sys.stderr)
                print("Run: cd .claude/skills/excalidraw-diagram/references && uv run playwright install chromium", file=sys.stderr)
                sys.exit(1)
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
        json_str = json.dumps(data)
        result = page.evaluate(f"window.renderDiagram({json_str})")

        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown render error") if result else "renderDiagram returned null"
            print(f"ERROR: Render failed: {error_msg}", file=sys.stderr)
            browser.close()
            sys.exit(1)

        # Wait for render completion signal
        page.wait_for_function("window.__renderComplete === true", timeout=15000)

        # Screenshot the SVG element
        svg_el = page.query_selector("#root svg")
        if svg_el is None:
            print("ERROR: No SVG element found after render.", file=sys.stderr)
            browser.close()
            sys.exit(1)

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

    png_path = render(args.input, args.output, args.scale, args.width)
    print(str(png_path))


if __name__ == "__main__":
    main()
