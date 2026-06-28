import sys
import http.server
import socketserver
import webbrowser
import threading
import time
import json
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Excalidraw Diagram Dashboard</title>
  <style>
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
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    header h1 {
      margin: 0;
      font-size: 22px;
      font-weight: 800;
      letter-spacing: -0.025em;
    }
    header p {
      margin: 4px 0 0 0;
      font-size: 13px;
      opacity: 0.8;
    }
    main {
      padding: 40px;
      max-width: 1200px;
      margin: 0 auto;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 30px;
    }
    .card {
      background: white;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
      border: 1px solid #e2e8f0;
      transition: transform 0.2s, box-shadow 0.2s;
      display: flex;
      flex-direction: column;
    }
    .card:hover {
      transform: translateY(-4px);
      box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
    }
    .preview-container {
      height: 180px;
      background: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      border-bottom: 1px solid #e2e8f0;
      position: relative;
    }
    .preview-container img {
      max-width: 95%;
      max-height: 95%;
      object-fit: contain;
    }
    .preview-placeholder {
      color: #94a3b8;
      font-size: 13px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }
    .card-content {
      padding: 20px;
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .card-title {
      font-size: 16px;
      font-weight: 700;
      margin: 0 0 8px 0;
      color: #0f172a;
    }
    .card-meta {
      font-size: 11px;
      color: #64748b;
      margin-bottom: 16px;
      line-height: 1.5;
    }
    .card-actions {
      display: flex;
      gap: 10px;
    }
    .btn {
      flex: 1;
      padding: 8px 12px;
      border-radius: 6px;
      text-align: center;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn-primary {
      background: #2563eb;
      color: white;
      border: none;
    }
    .btn-primary:hover {
      background: #1d4ed8;
    }
    .btn-secondary {
      background: #f1f5f9;
      color: #334155;
      border: 1px solid #cbd5e1;
    }
    .btn-secondary:hover {
      background: #e2e8f0;
    }
    .empty-state {
      text-align: center;
      padding: 60px;
      background: white;
      border-radius: 12px;
      border: 2px dashed #cbd5e1;
      color: #64748b;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>🎨 Excalidraw Diagram Dashboard</h1>
      <p>Manage, edit, and export visual strategy models in your workspace</p>
    </div>
    <div style="font-size: 12px; opacity: 0.8; text-align: right;">
      Status: <strong>Online</strong><br/>
      Context: <strong>Local Workspace</strong>
    </div>
  </header>
  <main>
    [CONTENT_HERE]
  </main>
</body>
</html>
"""

def generate_dashboard(directory: Path):
    excalidraw_files = []
    # Scan the given directory recursively for .excalidraw files
    for p in directory.glob('**/*.excalidraw'):
        # Check relative path parts to allow files inside a parent .gemini directory
        rel_parts = p.relative_to(directory).parts
        if any(x in rel_parts for x in ['.venv', 'node_modules', '.git', 'scratch', '.gemini', '.tempmediaStorage']):
            continue
        excalidraw_files.append(p)
        
    excalidraw_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not excalidraw_files:
        content = """
        <div class="empty-state">
          <h2>No Excalidraw diagrams found in this directory</h2>
          <p>Ask your coding agent to generate an Excalidraw diagram to populate this dashboard.</p>
        </div>
        """
    else:
        cards = []
        for p in excalidraw_files:
            rel_path = p.relative_to(directory)
            png_path = rel_path.with_suffix(".png")
            editor_path = rel_path.with_name(f"{rel_path.name}_editor.html")
            
            has_png = (directory / png_path).exists()
            has_editor = (directory / editor_path).exists()
            
            mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.stat().st_mtime))
            
            preview_html = f'<img src="{png_path}" alt="{p.name} preview" />' if has_png else """
            <div class="preview-placeholder">
              <span>📷 Preview not rendered</span>
              <span style="font-size: 10px;">Render the diagram to generate a PNG</span>
            </div>
            """
            
            editor_btn = f'<a class="btn btn-primary" href="{editor_path}">✏️ Open Editor</a>' if has_editor else """
            <button class="btn btn-primary" style="opacity: 0.5; cursor: not-allowed;" disabled>No Editor</button>
            """
            
            cards.append(f"""
            <div class="card">
              <div class="preview-container">
                {preview_html}
              </div>
              <div class="card-content">
                <div>
                  <h3 class="card-title">{p.stem.replace('_', ' ').replace('-', ' ').title()}</h3>
                  <div class="card-meta">
                    <strong>Path:</strong> <code>{rel_path}</code><br/>
                    <strong>Last modified:</strong> {mtime}
                  </div>
                </div>
                <div class="card-actions">
                  {editor_btn}
                  <a class="btn btn-secondary" href="{rel_path}" download>📐 Get JSON</a>
                </div>
              </div>
            </div>
            """)
        content = f'<div class="grid">{"".join(cards)}</div>'
        
    return TEMPLATE.replace('[CONTENT_HERE]', content)

def get_free_port():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def main():
    if len(sys.argv) >= 2:
        target_path = Path(sys.argv[1]).resolve()
        if target_path.is_file():
            directory = target_path.parent
            filename = target_path.name
            single_file_mode = True
        else:
            directory = target_path
            filename = "index.html"
            single_file_mode = False
    else:
        directory = Path('.').resolve()
        filename = "index.html"
        single_file_mode = False
        
    port = get_free_port()
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
            
        def do_GET(self):
            # Intercept root path to dynamically serve the dashboard if not in single-file mode
            if not single_file_mode and self.path in ['', '/', '/index.html']:
                try:
                    html_content = generate_dashboard(directory)
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(html_content.encode('utf-8'))
                except Exception as e:
                    self.send_error(500, f"Error generating dashboard: {e}")
            else:
                super().do_GET()
                
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("", port), Handler)
    
    print(f"Starting server at http://localhost:{port} serving {directory}")
    
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    
    # Open browser
    url = f"http://localhost:{port}/{filename}"
    print(f"Opening browser at {url}...")
    webbrowser.open(url)
    
    print("Press Ctrl+C to stop the server.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.shutdown()

if __name__ == "__main__":
    main()
