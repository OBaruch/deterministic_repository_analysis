"""Dependency-free HTML rendering of the Markdown reports and optional PDF printing."""

from __future__ import annotations

import csv
import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


_ESCAPABLE = r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""
_ESCAPE_OR_CODE = re.compile(r"\\([" + re.escape(_ESCAPABLE) + r"])|(`+)(.+?)(?<!`)\2(?!`)")


def _table_cells(line: str) -> list[str]:
    """Split a Markdown table row on unescaped pipes, keeping other escapes intact."""
    content = line.strip()
    content = content[1:] if content.startswith("|") else content
    content = content[:-1] if content.endswith("|") and not content.endswith("\\|") else content
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in content:
        if escaped:
            current.append(character if character == "|" else "\\" + character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _local_uri(output: Path, base: Path, target: str) -> str:
    target_path = (base / target).resolve()
    try:
        target_path.relative_to(output.resolve())
    except ValueError as error:
        raise RuntimeError(f"PDF source link escapes output directory: {target}") from error
    if not target_path.exists():
        raise RuntimeError(f"PDF source link does not exist: {target_path}")
    return target_path.as_uri()


def _inline(output: Path, base: Path, text: str) -> str:
    placeholders: list[str] = []

    def preserve(value: str) -> str:
        token = f"\x00{len(placeholders)}\x00"
        placeholders.append(value)
        return token

    def image(match: re.Match[str]) -> str:
        alt = html.escape(match.group(1), quote=True)
        source = html.escape(_local_uri(output, base, match.group(2)), quote=True)
        return preserve(
            f'<figure><img src="{source}" alt="{alt}"><figcaption>{alt}</figcaption></figure>'
        )

    def link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        target = match.group(2)
        href = (
            target
            if "://" in target or target.startswith("#")
            else _local_uri(output, base, target)
        )
        return preserve(f'<a href="{html.escape(href, quote=True)}">{label}</a>')

    def escape_or_code(match: re.Match[str]) -> str:
        if match.group(1) is not None:
            return preserve(html.escape(match.group(1)))
        return preserve(f"<code>{html.escape(match.group(3).strip())}</code>")

    # Backslash escapes and code spans are resolved together, left to right, as in CommonMark.
    text = re.sub(_ESCAPE_OR_CODE, escape_or_code, text)
    text = re.sub(r"!\[([^]]*)\]\(([^)]+)\)", image, text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", link, text)
    rendered = html.escape(text)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    # Later placeholders may wrap earlier ones (for example a link label), so expand in reverse.
    for index in reversed(range(len(placeholders))):
        rendered = rendered.replace(f"\x00{index}\x00", placeholders[index])
    return rendered


def markdown_to_html(output: Path, path: Path, section_id: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    rendered = [f'<section class="document" id="{section_id}">']
    paragraph: list[str] = []
    items: list[str] = []
    code_lines: list[str] = []
    in_code = False
    index = 0

    def flush() -> None:
        if paragraph:
            rendered.append(f"<p>{_inline(output, path.parent, ' '.join(paragraph))}</p>")
            paragraph.clear()
        if items:
            rendered.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
            items.clear()

    while index < len(lines):
        line = lines[index]
        if in_code:
            if line.startswith("```"):
                rendered.append(
                    "<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>"
                )
                code_lines.clear()
                in_code = False
            else:
                code_lines.append(line)
            index += 1
            continue
        if line.startswith("```"):
            flush()
            in_code = True
            index += 1
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            rendered.append(
                f"<h{level}>{_inline(output, path.parent, heading.group(2))}</h{level}>"
            )
            index += 1
            continue
        if line.startswith("- "):
            if paragraph:
                flush()
            items.append(_inline(output, path.parent, line[2:]))
            index += 1
            continue
        if (
            line.startswith("|")
            and index + 1 < len(lines)
            and re.match(r"^\|[\s:|-]+\|$", lines[index + 1])
        ):
            flush()
            headers = _table_cells(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append(_table_cells(lines[index]))
                index += 1
            rendered.append('<div class="table-wrap"><table><thead><tr>')
            rendered.extend(f"<th>{_inline(output, path.parent, cell)}</th>" for cell in headers)
            rendered.append("</tr></thead><tbody>")
            for row in rows:
                rendered.append("<tr>")
                rendered.extend(f"<td>{_inline(output, path.parent, cell)}</td>" for cell in row)
                rendered.append("</tr>")
            rendered.append("</tbody></table></div>")
            continue
        if not line.strip():
            flush()
        else:
            paragraph.append(line.strip())
        index += 1
    flush()
    if in_code:
        raise RuntimeError(f"Unclosed Markdown code block: {path}")
    rendered.append("</section>")
    return "\n".join(rendered)


def _stylesheet() -> str:
    return """
@page { size: A4 landscape; margin: 12mm 12mm 13mm; }
@media print { .document { break-before: page; } .cover, .toc { break-after: page; } a { color: inherit; text-decoration: none; } }
:root { --ink:#18232d; --muted:#586877; --line:#cfd8df; --soft:#edf3f5; --teal:#0b6e75; --coral:#c8553d; }
* { box-sizing:border-box; }
body { margin:0; color:var(--ink); background:#fff; font:10pt/1.4 "Segoe UI","Aptos",sans-serif; print-color-adjust:exact; -webkit-print-color-adjust:exact; }
.cover { min-height:178mm; padding:12mm 14mm; display:flex; flex-direction:column; justify-content:center; border:1px solid var(--line); }
.cover-rule { width:28mm; height:3mm; background:var(--coral); margin-bottom:8mm; }
.eyebrow { margin:0 0 4mm; color:var(--teal); font-size:12pt; font-weight:700; text-transform:uppercase; letter-spacing:1.2px; }
.cover h1 { margin:0; font-size:34pt; line-height:1.04; max-width:210mm; }
.subtitle { margin:7mm 0 13mm; color:var(--muted); font-size:15pt; }
.cover-metrics { display:grid; grid-template-columns:repeat(5,1fr); gap:5mm; }
.cover-metrics div { border-top:1.5mm solid var(--teal); padding-top:3mm; }
.cover-metrics strong { display:block; font-size:22pt; line-height:1; }
.cover-metrics span { display:block; margin-top:2mm; color:var(--muted); font-size:8pt; text-transform:uppercase; }
.toc { min-height:178mm; padding:12mm 10mm; }
.toc h1 { font-size:27pt; }
.toc ol { list-style:none; padding:0; max-width:220mm; border-top:1px solid var(--line); }
.toc li { border-bottom:1px solid var(--line); }
.toc a { display:flex; gap:7mm; padding:4mm 1mm; color:var(--ink); font-size:13pt; text-decoration:none; }
.toc a span { color:var(--coral); font-weight:700; }
.document { padding:0 1mm; }
h1 { margin:0 0 6mm; padding-bottom:3mm; border-bottom:1.5mm solid var(--teal); font-size:24pt; }
h2 { margin:8mm 0 3mm; color:var(--teal); font-size:15pt; break-after:avoid; }
h3 { margin:6mm 0 2mm; font-size:11pt; break-after:avoid; }
p { margin:2.5mm 0; } ul { margin:2mm 0 4mm; padding-left:6mm; } li { margin:1mm 0; }
code { padding:.2mm 1mm; border-radius:1mm; background:var(--soft); font-family:Consolas,monospace; font-size:8pt; overflow-wrap:anywhere; }
pre { margin:3mm 0; padding:4mm; border-left:1.5mm solid var(--coral); background:#f4f6f7; white-space:pre-wrap; break-inside:avoid; }
.table-wrap { margin:3mm 0 6mm; } table { width:100%; border-collapse:collapse; font-size:7.2pt; }
thead { display:table-header-group; } tr { break-inside:avoid; }
th { padding:1.7mm 1.6mm; color:#fff; background:var(--teal); text-align:left; vertical-align:bottom; }
td { padding:1.35mm 1.6mm; border-bottom:.25mm solid var(--line); vertical-align:top; overflow-wrap:anywhere; }
tbody tr:nth-child(even) td { background:#f5f8f9; }
figure { margin:5mm auto 7mm; break-inside:avoid; text-align:center; }
figure img { display:block; max-width:100%; max-height:158mm; margin:0 auto; }
figcaption { margin-top:1.5mm; color:var(--muted); font-size:8pt; }
"""


def build_html(output: Path, title: str) -> Path:
    repositories = _read_csv(output / "repository_summary.csv")
    documents = [
        (output / "REPORT.md", "Executive summary"),
        (output / "reports" / "global-summary.md", "Global summary"),
    ]
    documents.extend(
        (output / "reports" / f"{row['Repository']}.md", row["Repository"]) for row in repositories
    )
    documents.append((output / "METHODOLOGY.md", "Methodology and reproducibility"))
    missing = [path for path, _ in documents if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing PDF report sources: {missing}")
    total_files = sum(int(row["Total Files"]) for row in repositories)
    total_sources = sum(int(row["Source Files"]) for row in repositories)
    total_loc = sum(int(row["Lines of Code"]) for row in repositories)
    total_commits = sum(int(row["Unique Commits"]) for row in repositories)
    cover = f"""
<section class="cover"><div class="cover-rule"></div><p class="eyebrow">Deterministic repository audit</p>
<h1>{html.escape(title)}</h1><p class="subtitle">Quantitative code, history, language, and developer contribution analysis</p>
<div class="cover-metrics"><div><strong>{len(repositories):,}</strong><span>Repositories</span></div>
<div><strong>{total_files:,}</strong><span>Tracked files</span></div><div><strong>{total_sources:,}</strong><span>Source files</span></div>
<div><strong>{total_loc:,}</strong><span>Lines of code</span></div><div><strong>{total_commits:,}</strong><span>Commit count sum</span></div></div></section>
"""
    sections = []
    toc_items = []
    for index, (path, label) in enumerate(documents, start=1):
        section_id = f"section-{index}"
        toc_items.append(
            f'<li><a href="#{section_id}"><span>{index:02d}</span>{html.escape(label)}</a></li>'
        )
        sections.append(markdown_to_html(output, path, section_id))
    toc = '<section class="toc"><h1>Contents</h1><ol>' + "".join(toc_items) + "</ol></section>"
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{_stylesheet()}</style></head><body>"
        + cover
        + toc
        + "".join(sections)
        + "</body></html>"
    )
    html_path = output / "repo-audit-report.html"
    html_path.write_text(document, encoding="utf-8", newline="\n")
    return html_path


def _browser() -> Path:
    configured = os.environ.get("REPO_AUDIT_BROWSER", "")
    candidates = [configured] if configured else []
    candidates.extend(
        ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium", "chromium-browser")
    )
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
        found = shutil.which(candidate)
        if found:
            return Path(found).resolve()
    if os.name == "nt":
        for variable, executable in (
            ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
        ):
            path = Path(os.environ.get(variable, "")) / executable
            if os.environ.get(variable) and path.is_file():
                return path.resolve()
    raise RuntimeError(
        "No Chromium-based browser found for PDF generation. "
        "Set REPO_AUDIT_BROWSER or use --no-pdf."
    )


def _browser_arguments(browser: Path, profile: str, pdf_path: Path, html_path: Path) -> list[str]:
    arguments = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--no-pdf-header-footer",
        f"--user-data-dir={profile}",
    ]
    # Chromium refuses to start as root (for example in containers) unless its sandbox is off.
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        arguments.append("--no-sandbox")
    arguments.extend((f"--print-to-pdf={pdf_path}", html_path.as_uri()))
    return arguments


def build_pdf(output: Path, title: str) -> Path:
    html_path = build_html(output, title)
    pdf_path = output / "repo-audit-report.pdf"
    pdf_path.unlink(missing_ok=True)
    browser = _browser()
    with tempfile.TemporaryDirectory(prefix="repo-audit-browser-") as profile:
        result = subprocess.run(
            _browser_arguments(browser, profile, pdf_path, html_path),
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Browser PDF generation failed: {result.stderr.strip()}")
    payload = pdf_path.read_bytes()
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-2048:]:
        raise RuntimeError("Generated file is not a complete PDF")
    return pdf_path
