"""Export du rapport : docs/rapport.md -> docs/rapport.html -> docs/rapport.pdf.

Le Markdown est converti en HTML (mistune), avec une feuille de style d'impression et le rendu
des schémas Mermaid ; le PDF est ensuite produit par Chrome (ou Edge) en mode headless. Sous WSL,
le Chrome de Windows est utilisé avec des chemins convertis par wslpath.

Usage :
    python docs/build_report.py            # HTML + PDF
    python docs/build_report.py --html     # HTML seulement
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

import mistune

DOCS = Path(__file__).resolve().parent
SOURCE = DOCS / "rapport.md"
HTML_OUT = DOCS / "rapport.html"
PDF_OUT = DOCS / "rapport.pdf"

BROWSERS = [
    "google-chrome",
    "chromium",
    "chromium-browser",
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
]

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
:root { --ink: #1f2328; --ink-2: #57606a; --rule: #d8dee4; --accent: #1c5cab; --soft: #f3f6fa; }
body { font-family: "Segoe UI", "DejaVu Sans", system-ui, sans-serif; color: var(--ink);
       font-size: 10pt; line-height: 1.5; max-width: 180mm; margin: 0 auto; }
h1 { font-size: 21pt; margin: 0 0 4pt; line-height: 1.15; }
h1 + p strong { font-size: 12.5pt; color: var(--accent); }
h2 { font-size: 14pt; margin-top: 18pt; padding-bottom: 3pt; border-bottom: 2px solid var(--ink);
     break-after: avoid; }
h3 { font-size: 11.5pt; margin-top: 12pt; color: var(--accent); break-after: avoid; }
p, li { orphans: 3; widows: 3; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.6pt;
        break-inside: avoid; }
th, td { border-bottom: 1px solid var(--rule); padding: 3.5pt 5pt; text-align: left;
         vertical-align: top; }
th { background: var(--soft); font-weight: 600; }
td:not(:first-child) { font-variant-numeric: tabular-nums; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3px solid var(--rule);
             color: var(--ink-2); background: #fafbfc; }
code { font-family: "Cascadia Mono", "DejaVu Sans Mono", monospace; font-size: 8.4pt;
       background: var(--soft); padding: 0 2pt; border-radius: 2pt; }
pre { background: var(--soft); padding: 6pt 8pt; overflow-x: auto; font-size: 8pt;
      break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%; display: block; margin: 6pt auto 10pt; break-inside: avoid; }
pre.mermaid { background: none; text-align: center; }
hr { border: none; border-top: 1px solid var(--rule); margin: 14pt 0; }
h2#résumé-exécutif, h2:first-of-type { break-before: auto; }
"""

MERMAID = """
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({ startOnLoad: false, theme: "neutral", fontFamily: "Segoe UI, sans-serif" });
  mermaid.run({ querySelector: "pre.mermaid" }).then(() => { document.body.dataset.ready = "1"; });
</script>
"""


def to_html(markdown_text: str) -> str:
    render = mistune.create_markdown(plugins=["table", "strikethrough"], escape=False)
    body = render(markdown_text)
    # blocs ```mermaid -> <pre class="mermaid"> (rendus par mermaid.js)
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<pre class="mermaid">{m.group(1)}</pre>',
        body,
        flags=re.DOTALL,
    )
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<title>Rapport de mise en place et d'évaluation du système RAG</title>"
        f"<style>{CSS}</style></head><body>{body}{MERMAID}</body></html>"
    )


def find_browser() -> str:
    for candidate in BROWSERS:
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "Aucun navigateur Chrome / Chromium / Edge trouvé pour l'export PDF"
    )


def native_path(path: Path, browser: str) -> str:
    """Chemin compréhensible par le navigateur (chemin Windows si navigateur Windows sous WSL)."""
    if browser.startswith("/mnt/"):
        return subprocess.run(
            ["wslpath", "-w", str(path)], capture_output=True, text=True, check=True
        ).stdout.strip()
    return str(path)


def to_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = find_browser()
    native = native_path(html_path, browser).replace("\\", "/")
    # chemin réseau WSL (//wsl.localhost/...) -> file://wsl.localhost/... ; sinon file:///C:/...
    url = (
        "file:" + native if native.startswith("//") else "file:///" + native.lstrip("/")
    )
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=15000",  # laisse mermaid.js rendre les schémas
            f"--print-to-pdf={native_path(pdf_path, browser)}",
            url,
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export du rapport en HTML et PDF")
    parser.add_argument("--html", action="store_true", help="Ne produire que le HTML")
    args = parser.parse_args()
    HTML_OUT.write_text(to_html(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"HTML : {HTML_OUT}")
    if not args.html:
        to_pdf(HTML_OUT, PDF_OUT)
        print(f"PDF  : {PDF_OUT}")


if __name__ == "__main__":
    main()
