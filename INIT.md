# Excalidraw Generator Skill Init

## Purpose

This repository is a Codex/agent skill for creating Excalidraw diagrams that make a visual argument instead of laying out generic boxes. It combines diagram-design rules, Excalidraw JSON templates, a color system, and a Playwright renderer so an agent can generate `.excalidraw` files, render them to PNG, inspect the result, and iterate.

## Current Repo Shape

- `SKILL.md` is the primary runtime instruction file. It defines the trigger, visual design process, mandatory visualization-selection gate, section-by-section generation strategy, render/inspect/fix loop, and Tuftefy refinement rules.
- `README.md` is human-facing project documentation, attribution, and setup guidance.
- `references/color-palette.md` is the single source of truth for all normal and Tuftefy colors.
- `references/element-templates.md` contains copyable Excalidraw element JSON templates.
- `references/json-schema.md` summarizes the Excalidraw properties the skill relies on.
- `references/excalidraw_workspace.py` creates and manages one diagram workspace with `inputs/`, `diagrams/`, `exports/`, a manifest, Google Doc tab intake, render-all support, preflight checks, and a daemonized dashboard launcher.
- `references/render_excalidraw.py` validates `.excalidraw` JSON, renders it with Playwright, writes a PNG, and generates a companion local editor HTML file.
- `references/render_template.html` is the browser-side Excalidraw export wrapper used by the renderer.
- `references/serve_editor.py` starts a local dashboard/editor server for `.excalidraw` files under a chosen directory, generates missing editor HTML files, and exposes preview refresh controls.
- `references/pyproject.toml` defines the Python/Playwright runtime dependencies for the helper scripts. The runtime environment is intentionally rooted in `references/`.

## Bootstrap

From this checkout:

```bash
cd /Users/sameer.bajaj/PARA/Projects/python/pers_projects/excalidraw-generator/references
uv sync
uv run playwright install chromium
```

Basic script sanity check:

```bash
cd /Users/sameer.bajaj/PARA/Projects/python/pers_projects/excalidraw-generator/references
python3 -m py_compile render_excalidraw.py serve_editor.py
```

Create a diagram workspace:

```bash
cd /Users/sameer.bajaj/PARA/Projects/python/pers_projects/excalidraw-generator/references
uv run python excalidraw_workspace.py doctor /path/to/excalidraw-workspace
uv run python excalidraw_workspace.py init /path/to/excalidraw-workspace
uv run python excalidraw_workspace.py new /path/to/excalidraw-workspace --title "Strategy Diagram" --source /path/to/source.md
```

Create a diagram workspace from a Google Doc tab:

```bash
cd /Users/sameer.bajaj/PARA/Projects/python/pers_projects/excalidraw-generator/references
uv run python excalidraw_workspace.py from-gdoc /path/to/excalidraw-workspace \
  --url "https://docs.google.com/document/d/DOC_ID/edit?tab=t.TAB_ID" \
  --title "Strategy Diagram" \
  --render \
  --serve \
  --no-browser
```

Render a diagram:

```bash
cd /Users/sameer.bajaj/PARA/Projects/python/pers_projects/excalidraw-generator/references
uv run python render_excalidraw.py /path/to/diagram.excalidraw
```

Open the dashboard/editor for a workspace:

```bash
cd /Users/sameer.bajaj/PARA/Projects/python/pers_projects/excalidraw-generator/references
uv run python excalidraw_workspace.py serve /path/to/excalidraw-workspace --daemon --no-browser
```

## Operating Rules For Future Agents

1. Read `SKILL.md` first.
2. Read `references/color-palette.md` before choosing any colors.
3. Use `references/element-templates.md` for JSON shapes instead of inventing element structure from memory.
4. For technical diagrams, research the real protocol/API/schema names before drawing.
5. Before generating Excalidraw JSON, offer three visualization metaphors and ask the user to choose one, including whether to Tuftefy from the start.
6. For comprehensive diagrams, build one visual section at a time with descriptive IDs and section-scoped seeds.
7. Save the final `.excalidraw` file under the workspace `diagrams/` directory and keep the captured source text under `inputs/`.
8. After each generation or structural edit, render to PNG, inspect the image, fix defects, and repeat until the result is presentable.
9. When editing an existing diagram, modify the same file unless the user explicitly asks for a different diagram type.
10. Keep the visual methodology, pattern library, color palette, and element templates aligned with the upstream Coleam skill unless the user explicitly asks to change the design language.

## Known Friction

- `.github.json` still points at the upstream `coleam00/excalidraw-diagram-skill` metadata and says `hasWriteAccess: false`. Treat it as sync metadata, not authoritative repo identity.
- The renderer depends on CDN-hosted Excalidraw/React modules. The fork pins Excalidraw `0.18.0` and uses `bundle-deps`, which fixes the upstream timeout class, but first render still needs network access unless dependencies are cached.
- `serve_editor.py` includes a delete endpoint for `.excalidraw`, matching `.png`, and companion editor HTML files. Only run it against trusted local directories.

## Recommended Next Cleanup

1. Add `agents/openai.yaml` if this skill will be installed as a Codex skill with UI metadata.
2. Add a tiny sample `.excalidraw` fixture so renderer smoke tests can exercise the full Playwright path.
3. Decide whether helper scripts should stay under `references/` for compatibility or move to `scripts/` with compatibility shims.
4. If the helpers become importable library code, create a real Python package and then add `__init__.py`; do not add a symbolic package init while the repo is still script-oriented.
