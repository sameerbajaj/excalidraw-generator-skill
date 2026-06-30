# Excalidraw Generator Skill

A coding agent skill that empowers AI coding assistants (like Gemini, Claude Code, Cline, and others) to generate beautiful, structured, and practical Excalidraw diagrams from natural language descriptions. 

Rather than just displaying plain boxes and generic layouts, this skill uses specific design methodologies to help agents create diagrams that **argue visually**.

---

## 🚀 Key Improvements & Bug Fixes

This repository is a fork of the original [excalidraw-diagram-skill](https://github.com/coleam00/excalidraw-diagram-skill) by [@coleam00](https://github.com/coleam00) and includes critical updates:

*   **Fixed CDN Import/Playwright Timeout Bug:** The original skill's render template relied on an unpinned `https://esm.sh/@excalidraw/excalidraw?bundle` import. Recent CDN changes caused transitives (like `@braintree/sanitize-url`) to return 404s, leading to a silent 30-second Playwright timeout during initialization. This fork resolves that by **pinning version 0.18.0** and using esm.sh's **`?bundle-deps`** flag to bundle dependencies statically at build-time.
*   **Self-Contained References:** Standardized absolute and relative execution paths inside `SKILL.md` to ensure the Python renderer resolves successfully.

---

## 🎨 What Makes This Skill Different

1.  **Arguments Over Layouts:** Instead of rendering uniform card grids, the agent maps concepts to specialized visual models:
    *   *Timeline/Sequence:* Horizontal or vertical lines with dots and free-floating text labels.
    *   *Tree/Hierarchy:* Lines and branched sub-items (minimizing container clutter).
    *   *Fan-out & Convergence:* Directional arrows radiating from or collapsing into focal nodes.
2.  **Evidence Artifacts:** Diagrams contain concrete examples—such as language-appropriate syntax-highlighted code blocks, real JSON payload blocks, and actual spec-defined event names—rather than generic placeholders.
3.  **Visual Validation Loop:** Includes a Playwright-based Python script (`render_excalidraw.py`) that boots a headless Chromium instance to compile the `.excalidraw` JSON into a `.png` image. The agent inspects this image during generation to detect and fix text clippings, overlaps, or routing issues before presenting the file to the user.
4.  **Central Diagram Workspace:** The `excalidraw_workspace.py` helper captures source text or a Google Doc tab, stores diagrams in one workspace, renders previews, and starts a health-checked local dashboard/editor server.
5.  **Brand-Customizable:** A centralized color palette configuration (`references/color-palette.md`) dictates all shape colors, text colors, and background themes.

---

## 📦 File Structure

```
excalidraw-generator-skill/
  SKILL.md                          # Main skill instructions and visual workflow
  README.md                         # Project documentation and attribution (this file)
  .gitignore                        # Standard files, virtualenvs, and asset ignore rules
  references/
    color-palette.md                # Centralized color tokens (edit to change brand styling)
    element-templates.md            # Raw JSON chunks for shapes, arrows, lines, and text
    json-schema.md                  # Excalidraw element property reference
    excalidraw_workspace.py         # Workspace intake, manifest, render-all, and dashboard launcher
    render_excalidraw.py            # Playwright script to render diagram to PNG
    render_template.html            # Browser wrapper containing Excalidraw renderer
    serve_editor.py                 # Local dashboard/editor server
    pyproject.toml                  # Python package and dependency configurations
```

---

## ⚙️ Setup & Installation

Copy this directory into your agent's customization root folder (e.g., `.agents/skills/` or `.gemini/skills/` depending on your environment):

```bash
# Clone the repository
git clone https://github.com/sameerbajaj/excalidraw-generator-skill.git

# Move it into your agent skills path
mv excalidraw-generator-skill ~/.gemini/skills/excalidraw-generator-skill
```

### Install Rendering Dependencies

To enable the visual validation render loop, install the required packages:

```bash
cd ~/.gemini/skills/excalidraw-generator-skill/references
uv sync
uv run playwright install chromium
```

---

## 🗂️ Workspace Flow

Create one workspace for all generated diagrams:

```bash
cd ~/.gemini/skills/excalidraw-generator-skill/references
uv run python excalidraw_workspace.py doctor ~/excalidraw-workspace
uv run python excalidraw_workspace.py init ~/excalidraw-workspace
```

Capture source text and create a starter diagram target:

```bash
uv run python excalidraw_workspace.py new ~/excalidraw-workspace \
  --title "Strategy Model" \
  --source /path/to/strategy-notes.md
```

Capture a specific Google Doc tab through `gws`. For long docs, start with source capture and scope triage instead of generating one whole-document diagram:

```bash
uv run python excalidraw_workspace.py from-gdoc ~/excalidraw-workspace \
  --url "https://docs.google.com/document/d/DOC_ID/edit?tab=t.TAB_ID" \
  --title "Strategy Source" \
  --no-starter
```

After the user picks the target section and visual metaphor, create/render the diagram:

```bash
uv run python excalidraw_workspace.py from-gdoc ~/excalidraw-workspace \
  --url "https://docs.google.com/document/d/DOC_ID/edit?tab=t.TAB_ID" \
  --title "Chosen Section Diagram" \
  --render \
  --serve \
  --no-browser
```

Render previews and open the dashboard/editor server:

```bash
uv run python excalidraw_workspace.py render-all ~/excalidraw-workspace --scale 2 --width 1920
uv run python excalidraw_workspace.py serve ~/excalidraw-workspace --daemon --no-browser
```

The dashboard lists all `.excalidraw` files in the workspace, creates missing editor HTML files, refreshes PNG previews with scale/width controls, opens diagrams in the local editor, downloads JSON, and can delete a diagram plus its generated companions.

The workspace helper intentionally does not replace the diagram-design method inherited from `coleam00/excalidraw-diagram-skill`; it only removes the slow setup, Google Doc extraction, render, and server steps around that method.

---

## 🛠️ Usage

Simply instruct your coding agent:

> *"Generate an Excalidraw diagram showing how a client app establishes a WebSocket connection, authenticates, and handles incoming state-delta frames."*

The agent will load the generator skill, capture your source text into the workspace when appropriate, lay out the elements, output a `.excalidraw` JSON file, render it to a `.png` for inspection, fix any layout defects, and present the dashboard URL plus the saved files.

---

## 🤝 Credits & Attribution

This skill is built upon the wonderful foundation created by **[coleam00/excalidraw-diagram-skill](https://github.com/coleam00/excalidraw-diagram-skill)**. 

Special thanks to the original author, [@coleam00](https://github.com/coleam00), for designing the core Excalidraw visual-arguing methodology, color palette definitions, and playwright rendering pipeline framework.
