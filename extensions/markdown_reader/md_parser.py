# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Markdown to accessible plain-text converter.

Converts Markdown syntax into clean, screen-reader-friendly text while
preserving document structure (headings, lists, tables, code blocks).
No external dependencies — pure Python using only `re`.
"""

import re


# ── Dataclass-style container for a parsed heading ──────────────────────

class Heading:
    """Represents a heading extracted from the Markdown source."""

    __slots__ = ("level", "title", "line_index")

    def __init__(self, level, title, line_index):
        self.level = level          # int 1-6
        self.title = title          # str  (cleaned text)
        self.line_index = line_index  # int  (0-based position in *output* lines)

    def __repr__(self):
        return f"Heading(L{self.level}, {self.title!r}, line={self.line_index})"


# ── Inline cleanup helpers ──────────────────────────────────────────────

_INLINE_RULES = [
    # Images: ![alt](url) → alt
    (re.compile(r"!\[([^\]]*)\]\([^)]+\)"), r"\1"),
    # Links: [text](url) → text (url)
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r"\1 (\2)"),
    # Bold + italic: ***text*** or ___text___
    (re.compile(r"(\*{3}|_{3})(.+?)\1"), r"\2"),
    # Bold: **text** or __text__
    (re.compile(r"(\*{2}|_{2})(.+?)\1"), r"\2"),
    # Italic: *text* or _text_
    (re.compile(r"(?<!\w)(\*|_)(.+?)\1(?!\w)"), r"\2"),
    # Strikethrough: ~~text~~
    (re.compile(r"~~(.+?)~~"), r"\1"),
    # Inline code: `code`
    (re.compile(r"`([^`]+)`"), r"\1"),
    # HTML tags (simple strip)
    (re.compile(r"<[^>]+>"), ""),
]


def _clean_inline(text):
    """Strip inline Markdown formatting from *text*."""
    for pattern, replacement in _INLINE_RULES:
        text = pattern.sub(replacement, text)
    return text


# ── Block-level parser ──────────────────────────────────────────────────

def parse(source):
    """Parse a Markdown string and return ``(plain_text, headings)``.

    Parameters
    ----------
    source : str
        Raw Markdown text.

    Returns
    -------
    text : str
        Cleaned plain-text version of the document.
    headings : list[Heading]
        Heading objects with ``level``, ``title``, and ``line_index``
        (0-based line number in *text*).
    """
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []        # output lines
    headings = []   # collected Heading instances
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i]
        stripped = line.strip()

        # ── Fenced code block (``` or ~~~) ──────────────────────────
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            lang = stripped[3:].strip()
            if lang:
                out.append(f"[Code: {lang}]")
            else:
                out.append("[Code]")
            i += 1
            while i < total:
                if lines[i].strip().startswith(fence):
                    break
                out.append(lines[i])
                i += 1
            out.append("[/Code]")
            i += 1
            out.append("")
            continue

        # ── ATX headings (# … ######) ──────────────────────────────
        m = re.match(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$", line)
        if m:
            level = len(m.group(1))
            title = _clean_inline(m.group(2).strip())
            out.append("")  # blank line before heading
            heading_line_idx = len(out)
            out.append(title)
            out.append("—" * len(title))
            headings.append(Heading(level, title, heading_line_idx))
            i += 1
            continue

        # ── Setext heading (underline with === or ---) ─────────────
        if (
            i + 1 < total
            and stripped
            and re.match(r"^[=\-]{2,}\s*$", lines[i + 1].strip())
        ):
            level = 1 if lines[i + 1].strip()[0] == "=" else 2
            title = _clean_inline(stripped)
            out.append("")
            heading_line_idx = len(out)
            out.append(title)
            out.append("—" * len(title))
            headings.append(Heading(level, title, heading_line_idx))
            i += 2
            continue

        # ── Horizontal rule ────────────────────────────────────────
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            out.append("")
            out.append("─" * 40)
            out.append("")
            i += 1
            continue

        # ── Blockquote ─────────────────────────────────────────────
        if stripped.startswith(">"):
            quote_lines = []
            while i < total and lines[i].strip().startswith(">"):
                q = re.sub(r"^>\s?", "", lines[i].strip())
                quote_lines.append(_clean_inline(q))
                i += 1
            for ql in quote_lines:
                out.append(f"  │ {ql}")
            out.append("")
            continue

        # ── Table ──────────────────────────────────────────────────
        if "|" in stripped and stripped.startswith("|"):
            table_rows = []
            while i < total and "|" in lines[i].strip():
                row = lines[i].strip()
                # Skip separator rows (|---|---|)
                if re.match(r"^\|[\s\-:| ]+\|$", row):
                    i += 1
                    continue
                cells = [
                    _clean_inline(c.strip())
                    for c in row.strip("|").split("|")
                ]
                table_rows.append(cells)
                i += 1

            if table_rows:
                # Calculate column widths
                col_count = max(len(r) for r in table_rows)
                widths = [0] * col_count
                for row in table_rows:
                    for ci, cell in enumerate(row):
                        if ci < col_count:
                            widths[ci] = max(widths[ci], len(cell))

                # Render table
                for ri, row in enumerate(table_rows):
                    parts = []
                    for ci in range(col_count):
                        cell = row[ci] if ci < len(row) else ""
                        parts.append(cell.ljust(widths[ci]))
                    out.append("  " + " | ".join(parts))
                    # Separator after header row
                    if ri == 0:
                        sep_parts = ["—" * w for w in widths]
                        out.append("  " + "—+—".join(sep_parts))
                out.append("")
            continue

        # ── Unordered list item ────────────────────────────────────
        m = re.match(r"^(\s*)([-*+])\s+(.+)$", line)
        if m:
            indent = len(m.group(1)) // 2
            text = _clean_inline(m.group(3))
            prefix = "  " * indent + "• "
            out.append(f"{prefix}{text}")
            i += 1
            continue

        # ── Ordered list item ──────────────────────────────────────
        m = re.match(r"^(\s*)(\d+)[.)]\s+(.+)$", line)
        if m:
            indent = len(m.group(1)) // 2
            num = m.group(2)
            text = _clean_inline(m.group(3))
            prefix = "  " * indent + f"{num}. "
            out.append(f"{prefix}{text}")
            i += 1
            continue

        # ── Task list ──────────────────────────────────────────────
        m = re.match(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.+)$", line)
        if m:
            indent = len(m.group(1)) // 2
            checked = m.group(2).lower() == "x"
            text = _clean_inline(m.group(3))
            marker = "☑" if checked else "☐"
            prefix = "  " * indent
            out.append(f"{prefix}{marker} {text}")
            i += 1
            continue

        # ── Normal paragraph / blank line ──────────────────────────
        if not stripped:
            out.append("")
        else:
            out.append(_clean_inline(stripped))
        i += 1

    # Clean up excessive blank lines (max 2 consecutive)
    # Build a mapping from old line index → new line index so we can
    # fix up heading positions after lines are removed.
    cleaned = []
    old_to_new = {}   # old_index → new_index
    blank_count = 0
    for old_idx, line in enumerate(out):
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                old_to_new[old_idx] = len(cleaned)
                cleaned.append(line)
            # else: line is dropped, no mapping
        else:
            blank_count = 0
            old_to_new[old_idx] = len(cleaned)
            cleaned.append(line)

    # Strip leading/trailing blanks and track how many removed from front
    leading_removed = 0
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
        leading_removed += 1
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    # Remap heading line indices
    for h in headings:
        if h.line_index in old_to_new:
            h.line_index = max(0, old_to_new[h.line_index] - leading_removed)
        else:
            # Fallback: find the heading title in the cleaned output
            for new_idx, line in enumerate(cleaned):
                if line == h.title:
                    h.line_index = new_idx
                    break
            else:
                h.line_index = 0

    return "\n".join(cleaned), headings


# ── HTML inline conversion ──────────────────────────────────────────────

_HTML_INLINE_RULES = [
    # Images: ![alt](url)
    (re.compile(r"!\[([^\]]*)\]\(([^)]+)\)"), r'<img alt="\1" src="\2">'),
    # Links: [text](url)
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r'<a href="\2">\1</a>'),
    # Bold + italic: ***text***
    (re.compile(r"(\*{3}|_{3})(.+?)\1"), r"<strong><em>\2</em></strong>"),
    # Bold: **text**
    (re.compile(r"(\*{2}|_{2})(.+?)\1"), r"<strong>\2</strong>"),
    # Italic: *text*
    (re.compile(r"(?<!\w)(\*|_)(.+?)\1(?!\w)"), r"<em>\2</em>"),
    # Strikethrough: ~~text~~
    (re.compile(r"~~(.+?)~~"), r"<strike>\1</strike>"),
    # Inline code: `code`
    (re.compile(r"`([^`]+)`"), r"<tt>\1</tt>"),
]


def _html_escape(text):
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _html_inline(text):
    """Convert inline Markdown formatting to HTML."""
    # Escape HTML first, but preserve our converted tags after
    text = _html_escape(text)
    for pattern, replacement in _HTML_INLINE_RULES:
        text = pattern.sub(replacement, text)
    return text


def parse_to_html(source):
    """Parse Markdown and return ``(html_body, headings)``.

    The HTML is a fragment (no <html>/<body> wrapper) with semantic elements
    that NVDA's browse mode can navigate: <h1>-<h6>, <ul>/<ol>, <li>,
    <table>, <a>, <blockquote>, <pre><code>, etc.

    Parameters
    ----------
    source : str
        Raw Markdown text.

    Returns
    -------
    html : str
        Semantic HTML fragment.
    headings : list[Heading]
        Heading objects with ``level``, ``title``, and ``line_index``
        (sequential index, 0-based).
    """
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    headings = []
    i = 0
    total = len(lines)
    heading_count = 0

    # Track list state for proper nesting
    in_list = None  # None, 'ul', or 'ol'
    paragraph_lines = []  # Buffer for paragraph text

    def _flush_paragraph():
        if paragraph_lines:
            out.append("<p>" + " ".join(paragraph_lines) + "</p>")
            paragraph_lines.clear()

    def _close_list():
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    while i < total:
        line = lines[i]
        stripped = line.strip()

        # ── Fenced code block ──────────────────────────────────────
        if stripped.startswith("```") or stripped.startswith("~~~"):
            _flush_paragraph()
            _close_list()
            fence = stripped[:3]
            lang = stripped[3:].strip()
            lang_attr = f' class="language-{_html_escape(lang)}"' if lang else ""
            code_lines = []
            i += 1
            while i < total:
                if lines[i].strip().startswith(fence):
                    break
                code_lines.append(_html_escape(lines[i]))
                i += 1
            out.append(f"<pre><code{lang_attr}>{chr(10).join(code_lines)}</code></pre>")
            i += 1
            continue

        # ── ATX headings ───────────────────────────────────────────
        m = re.match(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$", line)
        if m:
            _flush_paragraph()
            _close_list()
            level = len(m.group(1))
            raw_title = m.group(2).strip()
            title = _clean_inline(raw_title)
            hid = f"heading-{heading_count}"
            out.append(f'<h{level} id="{hid}">{_html_inline(raw_title)}</h{level}>')
            headings.append(Heading(level, title, heading_count))
            heading_count += 1
            i += 1
            continue

        # ── Setext heading ─────────────────────────────────────────
        if (
            i + 1 < total
            and stripped
            and re.match(r"^[=\-]{2,}\s*$", lines[i + 1].strip())
        ):
            _flush_paragraph()
            _close_list()
            level = 1 if lines[i + 1].strip()[0] == "=" else 2
            title = _clean_inline(stripped)
            hid = f"heading-{heading_count}"
            out.append(f'<h{level} id="{hid}">{_html_inline(stripped)}</h{level}>')
            headings.append(Heading(level, title, heading_count))
            heading_count += 1
            i += 2
            continue

        # ── Horizontal rule ────────────────────────────────────────
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            _flush_paragraph()
            _close_list()
            out.append("<hr>")
            i += 1
            continue

        # ── Blockquote ─────────────────────────────────────────────
        if stripped.startswith(">"):
            _flush_paragraph()
            _close_list()
            quote_lines = []
            while i < total and lines[i].strip().startswith(">"):
                q = re.sub(r"^>\s?", "", lines[i].strip())
                quote_lines.append(_html_inline(q))
                i += 1
            out.append("<blockquote><p>" + "<br>".join(quote_lines) + "</p></blockquote>")
            continue

        # ── Table ──────────────────────────────────────────────────
        if "|" in stripped and stripped.startswith("|"):
            _flush_paragraph()
            _close_list()
            table_rows = []
            is_header = True
            while i < total and "|" in lines[i].strip():
                row = lines[i].strip()
                if re.match(r"^\|[\s\-:| ]+\|$", row):
                    i += 1
                    continue
                cells = [_html_inline(c.strip()) for c in row.strip("|").split("|")]
                table_rows.append((cells, is_header))
                is_header = False
                i += 1

            if table_rows:
                out.append('<table role="grid">')
                for cells, is_hdr in table_rows:
                    tag = "th" if is_hdr else "td"
                    row_html = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
                    if is_hdr:
                        out.append(f"<thead><tr>{row_html}</tr></thead><tbody>")
                    else:
                        out.append(f"<tr>{row_html}</tr>")
                out.append("</tbody></table>")
            continue

        # ── Task list ──────────────────────────────────────────────
        m = re.match(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.+)$", line)
        if m:
            _flush_paragraph()
            if in_list != "ul":
                _close_list()
                out.append('<ul role="list">')
                in_list = "ul"
            checked = 'checked disabled' if m.group(2).lower() == "x" else 'disabled'
            text = _html_inline(m.group(3))
            out.append(f'<li><input type="checkbox" {checked}> {text}</li>')
            i += 1
            continue

        # ── Unordered list item ────────────────────────────────────
        m = re.match(r"^(\s*)([-*+])\s+(.+)$", line)
        if m:
            _flush_paragraph()
            if in_list != "ul":
                _close_list()
                out.append('<ul role="list">')
                in_list = "ul"
            text = _html_inline(m.group(3))
            out.append(f"<li>{text}</li>")
            i += 1
            continue

        # ── Ordered list item ──────────────────────────────────────
        m = re.match(r"^(\s*)(\d+)[.)]\s+(.+)$", line)
        if m:
            _flush_paragraph()
            if in_list != "ol":
                _close_list()
                out.append('<ol role="list">')
                in_list = "ol"
            text = _html_inline(m.group(3))
            out.append(f"<li>{text}</li>")
            i += 1
            continue

        # ── Blank line ─────────────────────────────────────────────
        if not stripped:
            _flush_paragraph()
            _close_list()
            i += 1
            continue

        # ── Normal text (accumulate into paragraph) ────────────────
        paragraph_lines.append(_html_inline(stripped))
        i += 1

    _flush_paragraph()
    _close_list()

    return "\n".join(out), headings
