# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Guides (core 2.11): every extension may ship its own guide, and Hariku shows
it, like its own User Guide, as a web page with real headings. No wx here;
the windows are ui/guides_dialog.py.

    extensions/<id>/docs/<lang>/guide.md   an extension's guide, in Markdown;
                                           its first # heading is its title
    docs/<lang>/user_guide.txt             Hariku's own guide (CORE_ID)

    find_guide(ext_id, lang=None)   -> the guide's path in `lang` (default: the
                                       Hariku language), else in English, or None
    has_guide(ext_id)               -> bool
    list_guides()                   -> [(id, name)]: the installed extensions
                                       that have a guide, by name
    open_guide(ext_id)              -> the guide opens in the web browser; True
                                       when it did (CORE_ID: the User Guide)
    markdown_to_html(text, lang)    -> a guide as a whole, plain HTML page
    text_to_html(text, lang)        -> the same for the core's .txt documents

Why a page in the web browser
-----------------------------
NVDA users read long documents best in browse mode: H and Shift+H jump from
heading to heading, 1, 2 and 3 by level, Insert+F7 lists every heading and
Ctrl+F finds a word. A read-only text box (ui/document_viewer.py, where the
User Guide opened until 2.11) has none of that. So a guide becomes a small,
plain HTML page with real h1 to h3, lists and paragraphs, and a lang
attribute so the screen reader reads it in the right language; everything in
it is escaped and a Content-Security-Policy forbids scripts and anything
loaded from elsewhere. The page is written to Hariku's own temp folder and
opened with os.startfile(): the user's own browser, where browse mode is on
from the start. NVDA's own User Guide opens the same way.

That works the same from source and in the compiled (Nuitka) build, because
os.startfile is part of Python itself. core.webview's window doesn't: it
starts sys.executable with core/webview_host.py, and in the compiled build
sys.executable is Hariku.exe and webview_host.py isn't there, so a second
Hariku would start and the single-instance check would refuse it; its
wx.html2 window also needs the WebView2 runtime and loader DLL in the build.

Safety
------
An extension id is a folder name of letters, digits, "-" and "_"; a language
is a code like "en" or "pt-BR". A guide in a folder must resolve (realpath,
links followed) inside that extension's folder; one in a .hrk is read from
the archive by its fixed name, never unpacked. A guide over MAX_GUIDE_BYTES
isn't read.
"""
import html
import logging
import os
import re
import tempfile
import threading
import uuid
import zipfile

logger = logging.getLogger(__name__)

CORE_ID = "core"                    # Hariku's own User Guide
GUIDE_FILE = "guide.md"
CORE_GUIDE_FILE = "user_guide.txt"
FALLBACK_LANGUAGE = "en"
MAX_GUIDE_BYTES = 512 * 1024        # a guide is text; this is plenty
ARCHIVE_SUFFIX = ".hrk"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?$")
# Scripts written right to left: their page gets dir="rtl".
_RTL_LANGUAGES = {"ar", "he", "fa", "ur", "yi", "ps", "sd", "ug", "dv", "ckb"}


# ------------------------------------------------------------
# Finding a guide
# ------------------------------------------------------------

def valid_id(ext_id):
    return isinstance(ext_id, str) and bool(_ID_RE.match(ext_id))


def valid_language(lang):
    return isinstance(lang, str) and bool(_LANG_RE.match(lang))


def _current_language():
    try:
        from core.i18n import get_current_language
        lang = get_current_language()
    except Exception:
        lang = FALLBACK_LANGUAGE
    return lang if valid_language(lang) else FALLBACK_LANGUAGE


def _languages(lang):
    """The languages to look in, in order: `lang`, then English."""
    first = lang if valid_language(lang) else _current_language()
    return [first] if first == FALLBACK_LANGUAGE else [first, FALLBACK_LANGUAGE]


def _inside(path, folder):
    """Whether `path` is inside `folder`, both resolved (links followed)."""
    try:
        base = os.path.realpath(folder)
        real = os.path.realpath(path)
        return (os.path.normcase(os.path.commonpath([base, real])) == os.path.normcase(base)
                and os.path.normcase(real) != os.path.normcase(base))
    except ValueError:          # another drive
        return False


def _app_dir():
    # Hariku's folder: the source tree, or the compiled build's folder (Nuitka
    # gives compiled modules a __file__ where the .py would be), as i18n does.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def core_docs_dir():
    return os.path.join(_app_dir(), "docs")


def _scratchpad_dir():
    """The developer scratchpad, when it is on (it loads before everything)."""
    try:
        import core.api
        config = core.api.load_data("Core")
    except Exception:
        return None
    if not config.get("enable_scratchpad", False):
        return None
    import core.extension_manager as manager
    return config.get("scratchpad_dir", "") or manager.SCRATCHPAD_DIR


def extension_source(ext_id):
    """Where an installed extension's files are, as the extension loader
    prefers them: ("dir", folder) or ("hrk", file), or None."""
    if not valid_id(ext_id):
        return None
    import core.extension_manager as manager
    places = []
    scratchpad = _scratchpad_dir()
    if scratchpad:
        places.append(("dir", os.path.join(scratchpad, ext_id)))
    places += [("dir", os.path.join(manager.USER_EXTENSIONS_DIR, ext_id)),
               ("hrk", os.path.join(manager.USER_EXTENSIONS_DIR, ext_id + ARCHIVE_SUFFIX)),
               ("dir", os.path.join(manager.SYSTEM_EXTENSIONS_DIR, ext_id))]
    for kind, path in places:
        if kind == "dir" and os.path.isfile(os.path.join(path, "manifest.json")):
            return kind, path
        if kind == "hrk" and os.path.isfile(path):
            return kind, path
    return None


def _member(lang):
    return f"docs/{lang}/{GUIDE_FILE}"


def _guide_in_folder(folder, lang):
    path = os.path.join(folder, "docs", lang, GUIDE_FILE)
    if not os.path.isfile(path):
        return None
    if not _inside(path, folder):
        logger.warning(f"Guides: {path} leads outside its extension's folder; ignored.")
        return None
    try:
        if os.path.getsize(path) > MAX_GUIDE_BYTES:
            logger.warning(f"Guides: {path} is too big to show.")
            return None
    except OSError:
        return None
    return os.path.realpath(path)


def _guide_in_archive(archive, lang):
    try:
        with zipfile.ZipFile(archive) as z:
            if z.getinfo(_member(lang)).file_size > MAX_GUIDE_BYTES:
                logger.warning(f"Guides: {archive}'s {lang} guide is too big to show.")
                return None
    except (KeyError, OSError, zipfile.BadZipFile, RuntimeError):
        return None
    # As zipimport writes paths inside an archive: the archive, then the member.
    return os.path.join(archive, "docs", lang, GUIDE_FILE)


def _core_guide(lang):
    path = os.path.join(core_docs_dir(), lang, CORE_GUIDE_FILE)
    return path if os.path.isfile(path) else None


def _find(ext_id, lang=None):
    """(path, language) of a guide, or (None, None)."""
    if ext_id == CORE_ID:
        for code in _languages(lang):
            path = _core_guide(code)
            if path:
                return path, code
        return None, None
    source = extension_source(ext_id)
    if source is None:
        return None, None
    kind, where = source
    for code in _languages(lang):
        path = (_guide_in_folder(where, code) if kind == "dir"
                else _guide_in_archive(where, code))
        if path:
            return path, code
    return None, None


def find_guide(ext_id, lang=None):
    """The path of an installed extension's guide (CORE_ID: Hariku's User
    Guide) in `lang`, default the Hariku language, else in English; None when
    there is none. A guide inside a .hrk has the archive's path, then the
    member (as zipimport writes it): read it with read_guide()."""
    return _find(ext_id, lang)[0]


def has_guide(ext_id):
    return find_guide(ext_id) is not None


def guide_languages(ext_id):
    """The languages an installed extension's guide is written in."""
    return sorted(guide_titles(ext_id))


def _split_archive(path):
    """(archive, member) when `path` points inside a .hrk, else None."""
    lowered = path.lower()
    marker = ARCHIVE_SUFFIX + os.sep
    start = 0
    while True:
        index = lowered.find(marker, start)
        if index < 0:
            return None
        archive = path[:index + len(ARCHIVE_SUFFIX)]
        if os.path.isfile(archive):
            return archive, path[index + len(marker):].replace(os.sep, "/")
        start = index + 1


def _is_guide_member(member):
    parts = member.split("/")
    return (len(parts) == 3 and parts[0] == "docs" and valid_language(parts[1])
            and parts[2] == GUIDE_FILE)


def _decode(data):
    return data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def read_guide(path):
    """The text of a guide find_guide() returned, or None (missing, too big,
    unreadable)."""
    if not path:
        return None
    try:
        inside = _split_archive(path)
        if inside is not None:
            archive, member = inside
            if not _is_guide_member(member):
                return None
            with zipfile.ZipFile(archive) as z:
                info = z.getinfo(member)
                if info.file_size > MAX_GUIDE_BYTES:
                    logger.warning(f"Guides: {path} is too big to show.")
                    return None
                with z.open(info) as f:
                    data = f.read(MAX_GUIDE_BYTES + 1)
        else:
            if os.path.getsize(path) > MAX_GUIDE_BYTES:
                logger.warning(f"Guides: {path} is too big to show.")
                return None
            with open(path, "rb") as f:
                data = f.read(MAX_GUIDE_BYTES + 1)
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError) as e:
        logger.warning(f"Guides: reading {path} failed: {e}")
        return None
    if len(data) > MAX_GUIDE_BYTES:
        return None
    return _decode(data)


_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")


def guide_title(text):
    """The guide's title: its first # heading, as plain text ("" if none)."""
    in_fence = False
    for line in (text or "").split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        m = None if in_fence else _HEADING_RE.match(line)
        if m and len(m.group(1)) == 1:
            return _plain(_strip_closing_hashes(m.group(2) or ""))
    return ""


# Titles already read, by (path, modified, size): the Help list and Aruna
# read every installed guide's title.
_titles = {}
_titles_lock = threading.Lock()


def _stamp(path):
    inside = _split_archive(path)
    target = inside[0] if inside else path
    try:
        st = os.stat(target)
        return (path, st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def title_of(path):
    stamp = _stamp(path)
    with _titles_lock:
        if stamp is not None and stamp in _titles:
            return _titles[stamp]
    title = guide_title(read_guide(path) or "")
    if stamp is not None:
        with _titles_lock:
            if len(_titles) > 500:
                _titles.clear()
            _titles[stamp] = title
    return title


def installed_extensions():
    """{id: manifest name} of the installed extensions (those the Extension
    Manager lists, and any loaded from elsewhere, such as the scratchpad)."""
    import core.extension_manager as manager
    found = {}
    try:
        for info in manager.get_installed_extensions_info():
            if valid_id(info.get("id")):
                found[info["id"]] = str(info.get("name") or info["id"])
    except Exception:
        logger.exception("Guides: listing the installed extensions failed")
    for ext_id, data in list(manager.LOADED_EXTENSIONS.items()):
        if valid_id(ext_id) and ext_id not in found:
            manifest = (data or {}).get("manifest") or {}
            found[ext_id] = str(manifest.get("name") or ext_id)
    found.pop(CORE_ID, None)
    return found


# {language: title} of each .hrk's guides, by (archive, modified, size).
_archive_titles = {}


def guide_titles(ext_id):
    """{language: title} of an installed extension's guides ("" for a guide
    without a # title), reading its .hrk once."""
    source = extension_source(ext_id)
    if source is None:
        return {}
    kind, where = source
    found = {}
    try:
        if kind == "dir":
            docs = os.path.join(where, "docs")
            for code in sorted(os.listdir(docs)) if os.path.isdir(docs) else ():
                path = _guide_in_folder(where, code) if valid_language(code) else None
                if path:
                    found[code] = title_of(path)
            return found
        st = os.stat(where)
        key = (where, st.st_mtime_ns, st.st_size)
        with _titles_lock:
            if key in _archive_titles:
                return dict(_archive_titles[key])
        with zipfile.ZipFile(where) as z:
            for info in z.infolist():
                if _is_guide_member(info.filename) and info.file_size <= MAX_GUIDE_BYTES:
                    with z.open(info) as f:
                        data = f.read(MAX_GUIDE_BYTES + 1)
                    if len(data) <= MAX_GUIDE_BYTES:
                        found[info.filename.split("/")[1]] = guide_title(_decode(data))
    except (OSError, zipfile.BadZipFile, RuntimeError, KeyError):
        return {}
    with _titles_lock:
        if len(_archive_titles) > 200:
            _archive_titles.clear()
        _archive_titles[key] = dict(found)
    return found


def _shown_language(titles, lang=None):
    """The language find_guide() would open, of those in `titles`."""
    return next((code for code in _languages(lang) if code in titles), None)


def list_guides(lang=None):
    """[(id, name)] of the installed extensions that have a guide, by name.
    The name is the guide's title in the language shown (else the
    extension's name)."""
    guides = []
    for ext_id, name in installed_extensions().items():
        titles = guide_titles(ext_id)
        code = _shown_language(titles, lang)
        if code is not None:
            guides.append((ext_id, titles[code] or name))
    guides.sort(key=lambda item: (item[1].casefold(), item[0]))
    return guides


# ------------------------------------------------------------
# Markdown to HTML
# ------------------------------------------------------------
# A small subset, all a guide needs: # to ###### headings, paragraphs, "- "
# and "1. " lists (an item goes on over lines indented by two spaces or
# more), `code`, **bold**, ``` fenced blocks and --- rules. Everything else is
# text. Every character of the source is escaped before any tag is added, so
# nothing in a guide can become HTML.

_BULLET_RE = re.compile(r"^ {0,3}[-*+][ \t]+(.*)$")
_NUMBER_RE = re.compile(r"^ {0,3}(\d{1,9})[.)][ \t]+(.*)$")
_RULE_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_FENCE_RE = re.compile(r"^ {0,3}(```+|~~~+)")
_CODE_RE = re.compile(r"(`+)(.+?)\1", re.S)
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__", re.S)
_TAG_RE = re.compile(r"<[^>]*>")


def _escape(text):
    return html.escape(text, quote=True)


def _strip_closing_hashes(text):
    return re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", text).strip()


def _inline(text):
    """Escaped text with `code` and **bold**."""
    out = []
    pos = 0
    for m in _CODE_RE.finditer(text):
        out.append(_bold(_escape(text[pos:m.start()])))
        out.append(f"<code>{_escape(m.group(2).strip())}</code>")
        pos = m.end()
    out.append(_bold(_escape(text[pos:])))
    return "".join(out)


def _bold(escaped):
    return _BOLD_RE.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", escaped)


def _plain(text):
    """Inline Markdown as plain text (for a title)."""
    return html.unescape(_TAG_RE.sub("", _inline(text))).strip()


def markdown_body(text):
    """(body HTML, title) of a guide in Markdown."""
    out = []
    title = ""
    paragraph = []
    list_kind = None            # "ul" or "ol"
    item = None                 # the lines of the open list item

    def flush_paragraph():
        if paragraph:
            out.append("<p>" + _inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    def close_item():
        nonlocal item
        if item is not None:
            out.append("<li>" + _inline(" ".join(item)) + "</li>")
            item = None

    def close_list():
        nonlocal list_kind
        close_item()
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    def open_list(kind, start=1):
        nonlocal list_kind
        if list_kind != kind:
            close_list()
            attr = f' start="{start}"' if kind == "ol" and start != 1 else ""
            out.append(f"<{kind}{attr}>")
            list_kind = kind

    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].replace("\t", "    ")
        stripped = line.strip()
        fence = _FENCE_RE.match(line)
        if fence:
            flush_paragraph()
            close_list()
            marker = fence.group(1)
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(marker):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>" + _escape("\n".join(code)) + "</code></pre>")
            i += 1
            continue
        if not stripped:
            flush_paragraph()
            if list_kind:
                close_item()
                # A blank line ends the list unless another item follows.
                nxt = next((l for l in lines[i + 1:] if l.strip()), "")
                if not (_BULLET_RE.match(nxt) or _NUMBER_RE.match(nxt) or nxt.startswith("  ")):
                    close_list()
            i += 1
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            words = _strip_closing_hashes(heading.group(2) or "")
            if words:
                if level == 1 and not title:
                    title = _plain(words)
                out.append(f"<h{level}>{_inline(words)}</h{level}>")
            i += 1
            continue
        if _RULE_RE.match(line) and not paragraph:
            close_list()
            out.append("<hr>")
            i += 1
            continue
        bullet = _BULLET_RE.match(line)
        number = None if bullet else _NUMBER_RE.match(line)
        if bullet or number:
            flush_paragraph()
            if bullet:
                open_list("ul")
                words = bullet.group(1)
            else:
                open_list("ol", int(number.group(1)))
                words = number.group(2)
            close_item()
            item = [words.strip()]
            i += 1
            continue
        if item is not None:
            # The item goes on (indented, or a lazy continuation line).
            item.append(stripped)
            i += 1
            continue
        if list_kind:
            close_list()
        paragraph.append(stripped)
        i += 1
    flush_paragraph()
    close_list()
    return "\n".join(out), title


_STYLE = """
body { font-family: "Segoe UI", Calibri, Arial, sans-serif; font-size: 1.1rem;
       line-height: 1.6; max-width: 46rem; margin: 0 auto; padding: 1rem 1.5rem;
       color: #1a1a1a; background: #ffffff; }
h1, h2, h3, h4 { line-height: 1.3; margin: 1.4em 0 0.4em; }
h1 { font-size: 1.8rem; margin-top: 0.4em; }
h2 { font-size: 1.45rem; border-bottom: 1px solid #999; padding-bottom: 0.2em; }
h3 { font-size: 1.2rem; }
code, pre { font-family: Consolas, "Courier New", monospace; }
code { background: #eeeeee; padding: 0 0.25em; border-radius: 3px; }
pre { background: #f2f2f2; padding: 0.75em 1em; overflow-x: auto; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
li { margin: 0.25em 0; }
@media (prefers-color-scheme: dark) {
  body { color: #eeeeee; background: #1b1b1b; }
  h2 { border-color: #666; }
  code { background: #333333; }
  pre { background: #2a2a2a; }
}
"""


def page(body, title, lang="en"):
    """A whole HTML page around a body made by markdown_body() or
    text_body(): the language, the title, a plain style, and no scripts."""
    lang = lang if valid_language(lang) else FALLBACK_LANGUAGE
    lang = lang.replace("_", "-")
    direction = ' dir="rtl"' if lang.split("-")[0].lower() in _RTL_LANGUAGES else ""
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{_escape(lang)}"{direction}>\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_escape(title or 'Hariku')}</title>\n"
        f"<style>{_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n")


def markdown_to_html(text, lang="en", title=None):
    """A guide in Markdown as a whole HTML page. Its title is the guide's
    first # heading; `title` is used when it has none (and becomes its h1)."""
    body, found = markdown_body(text)
    if not found:
        found = title or "Hariku"
        body = f"<h1>{_escape(found)}</h1>\n{body}"
    return page(body, found, lang)


# ------------------------------------------------------------
# Hariku's own .txt documents to HTML
# ------------------------------------------------------------
# docs/<lang>/user_guide.txt is plain text: a title between two lines of
# "=", sections the same way, subsections underlined with "-". The first
# banner is the page's h1, the others h2, underlined lines h3. A block of
# lines at the left margin is a paragraph; indented lines (tables of keys,
# numbered steps) keep their layout in a <pre>.

_BANNER_RE = re.compile(r"^\s*={10,}\s*$")
_UNDERLINE_RE = re.compile(r"^\s*-{3,}\s*$")
_TEXT_ITEM_RE = re.compile(r"^( +)(?:([-*])|(\d{1,3})[.)])[ \t]+(\S.*)$")


def _text_list(run):
    """An indented run of lines as a <ul> or <ol> when it is one: every line
    an item ("  - Menu: ...", "  1. Hello.") of the same kind, or an item's
    continuation, indented further than the item's marker. Else None."""
    first = _TEXT_ITEM_RE.match(run[0])
    if not first:
        return None
    ordered = first.group(3) is not None
    indent = len(first.group(1))
    items = []
    for line in run:
        m = _TEXT_ITEM_RE.match(line)
        if m and len(m.group(1)) == indent and (m.group(3) is not None) == ordered:
            items.append([m.group(4).strip()])
        elif len(line) - len(line.lstrip(" ")) > indent:
            items[-1].append(line.strip())
        else:
            return None
    kind = "ol" if ordered else "ul"
    start = int(first.group(3)) if ordered else 1
    attr = f' start="{start}"' if ordered and start != 1 else ""
    return (f"<{kind}{attr}>\n"
            + "\n".join("<li>" + _escape(" ".join(item)) + "</li>" for item in items)
            + f"\n</{kind}>")


def text_body(text, title=""):
    """(body HTML, title) of one of Hariku's .txt documents."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    found_title = ""
    block = []

    def flush():
        run, indented = [], None
        for line in block + [None]:
            this = None if line is None else line[:1] in (" ", "\t")
            if line is None or (run and this != indented):
                if run:
                    if indented:
                        out.append(_text_list(run)
                                   or "<pre>" + _escape("\n".join(run)) + "</pre>")
                    else:
                        out.append("<p>" + _escape(" ".join(l.strip() for l in run)) + "</p>")
                run = []
            if line is not None:
                run.append(line.rstrip())
                indented = this
        block.clear()

    i = 0
    while i < len(lines):
        line = lines[i].replace("\t", "    ")
        if _BANNER_RE.match(line):
            flush()
            j = i + 1
            inner = []
            while j < len(lines) and not _BANNER_RE.match(lines[j]):
                inner.append(lines[j].strip())
                j += 1
            inner = [l for l in inner if l]
            if j < len(lines) and inner:
                if not found_title:
                    found_title = inner[0]
                    out.append(f"<h1>{_escape(inner[0])}</h1>")
                else:
                    out.append(f"<h2>{_escape(inner[0])}</h2>")
                if inner[1:]:
                    out.append("<p>" + _escape(" ".join(inner[1:])) + "</p>")
                i = j + 1
                continue
            i += 1
            continue
        if (line.strip() and i + 1 < len(lines) and _UNDERLINE_RE.match(lines[i + 1])
                and not block):
            out.append(f"<h3>{_escape(line.strip())}</h3>")
            i += 2
            continue
        if not line.strip():
            flush()
        else:
            block.append(line)
        i += 1
    flush()
    if not found_title:
        found_title = title or "Hariku"
        out.insert(0, f"<h1>{_escape(found_title)}</h1>")
    return "\n".join(out), found_title


def text_to_html(text, lang="en", title=""):
    body, found = text_body(text, title)
    return page(body, found, lang)


# ------------------------------------------------------------
# Opening a guide
# ------------------------------------------------------------

def pages_dir():
    """Hariku's temp area for the pages it opens (core.api allows HTML there)."""
    return os.path.join(tempfile.gettempdir(), "hariku2", "guides")


def guide_page(ext_id, lang=None):
    """(HTML page, title, language) of a guide, or None when there is none."""
    path, code = _find(ext_id, lang)
    text = read_guide(path) if path else None
    if text is None:
        return None
    if ext_id == CORE_ID:
        from core.i18n import get_translator
        body, title = text_body(text, get_translator("core")("menu_help_guide"))
        return page(body, title, code), title, code
    body, title = markdown_body(text)
    if not title:
        title = installed_extensions().get(ext_id, ext_id)
        body = f"<h1>{_escape(title)}</h1>\n{body}"
    return page(body, title, code), title, code


def write_page(html_text, name):
    """Write a page into pages_dir() as <name>.html, replacing the one
    written before (so reopening a guide doesn't pile up files); returns
    its path. When that file can't be replaced (another program holds it),
    the page gets a name of its own."""
    folder = pages_dir()
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(name))[:64] or "guide"
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(html_text)
        path = os.path.join(folder, safe + ".html")
        try:
            os.replace(tmp, path)
        except PermissionError:
            path = os.path.join(folder, f"{safe}-{uuid.uuid4().hex[:8]}.html")
            os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path


def _startfile(path):
    os.startfile(path)      # the user's default web browser for .html


def launch_page(path, launch=None):
    """Open a page written by write_page() in the web browser. Only pages in
    pages_dir() are opened."""
    if not _inside(path, pages_dir()) or not path.lower().endswith(".html"):
        logger.error(f"[Security] Guides: refusing to open {path}")
        return False
    try:
        (launch or _startfile)(path)
        return True
    except Exception as e:
        logger.error(f"Guides: opening {path} failed: {e}")
        return False


def open_guide(ext_id, lang=None, launch=None):
    """Open an installed extension's guide (CORE_ID: Hariku's User Guide) in
    the web browser, in the Hariku language or else in English. Returns True
    when it opened; False when there is no guide or it couldn't be opened."""
    made = guide_page(ext_id, lang)
    if made is None:
        return False
    html_text, _title, lang_used = made
    try:
        path = write_page(html_text, f"{ext_id}-{lang_used}")
    except OSError as e:
        logger.error(f"Guides: writing the page for {ext_id} failed: {e}")
        return False
    return launch_page(path, launch)


def open_core_guide(lang=None, launch=None):
    return open_guide(CORE_ID, lang, launch)


# ------------------------------------------------------------
# Aruna: "panduan orbit", "how to use dropbox"
# ------------------------------------------------------------
# A core command with content (core.commands.add_intent). The words after
# the pattern are matched loosely, as command names are, against every
# installed extension's id, name and guide titles (in the Hariku language and
# in English, and each part of a name: "Timer & Alarm" also answers to
# "alarm"). A clear match opens the guide once Aruna has closed, a close one
# is asked about first, and an extension without a guide says so. Anything
# else is turned down, so Aruna goes on as before: "bantuan bergerak" is
# nobody's guide, and "orbit bantuan" is Orbit's own in-game help (its
# pattern starts with "orbit").

GUIDE_INTENT = "Hariku Core.guide"
GUIDE_PATTERNS = (
    "panduan {text}", "buka panduan {text}", "cara pakai {text}", "cara menggunakan {text}",
    "bantuan {text}",
    "guide for {text}", "guide to {text}", "how to use {text}", "how do i use {text}",
    "help with {text}",
)
# Words that mean Hariku itself: "panduan hariku", "cara pakai aplikasi ini".
CORE_WORDS = {"hariku", "core", "inti", "pengguna", "user", "aplikasi", "app"}
_CORE_EXTRAS = {"ini", "this"}
_NAME_PARTS_RE = re.compile(r"\s*(?:&|\+|/|,|:|\(|\)|—|–|\s-\s|\band\b|\bdan\b)\s*", re.I)

_opener = None


def _name_parts(name):
    parts = [p.strip() for p in _NAME_PARTS_RE.split(name or "") if p and p.strip()]
    return parts if len(parts) > 1 else []


def guide_candidates(lang=None):
    """[(id, title, phrases, has a guide)] of every installed extension, for
    Aruna. The title is the guide's in the Hariku language (else in English,
    else the extension's name); the phrases have its titles in every language
    it is written in, since Aruna understands English and Indonesian whatever
    the Hariku language is."""
    found = []
    for ext_id, name in installed_extensions().items():
        titles = guide_titles(ext_id)
        code = _shown_language(titles, lang)
        phrases = [ext_id.replace("_", " ").replace("-", " "), name] + list(titles.values())
        for text in list(phrases):
            phrases += _name_parts(text)
        unique = list(dict.fromkeys(p for p in phrases if p))
        title = (titles[code] if code is not None else "") or name
        found.append((ext_id, title, unique, code is not None))
    return found


def match_guide(text, lang=None, candidates=None):
    """What "panduan <text>" asks for: (kind, id, title, has a guide), kind
    being "run" (clear), "ask" (close: ask first) or None (nobody's)."""
    import core.commands as commands
    said = commands.normalize(text).split()
    if not said:
        return None, None, None, False
    core_words = {commands.normalize(w) for w in CORE_WORDS}
    extras = {commands.normalize(w) for w in _CORE_EXTRAS}
    if all(w in core_words or w in extras or w in commands._FILLERS for w in said) \
            and any(w in core_words for w in said):
        from core.i18n import get_translator
        return "run", CORE_ID, get_translator("core")("menu_help_guide"), True
    candidates = guide_candidates(lang) if candidates is None else candidates
    said = commands.words(text)
    if not candidates or not said:
        return None, None, None, False
    ranked = sorted(((max((_name_score(said, commands.words(p, keep_all_fillers=True))
                           for p in phrases), default=0.0), ext_id, title, has)
                     for ext_id, title, phrases, has in candidates),
                    key=lambda item: (-item[0], item[1]))
    best, ext_id, title, has = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if best >= commands.RUN_SCORE and best - runner_up >= commands.RUN_MARGIN:
        return "run", ext_id, title, has
    if best >= commands.ASK_SCORE:
        return "ask", ext_id, title, has
    return None, None, None, False


NAME_WORD_FLOOR = 0.75      # how alike a word must be to a name's word to count


def _name_score(said, name):
    """0 to 1: how well the words said match a name's words, word by word
    (a misheard word still counts: "kalkulator" is 0.8 like "calculator").
    Stricter than command names: whole strings aren't compared letter by
    letter, and a word must be at least NAME_WORD_FLOOR like a name's word,
    so one that only sounds a bit like it ("sumpit", "tsunami") is nobody's."""
    from core.commands import _word_similarity

    def alike(a, b):
        s = _word_similarity(a, b)
        return s if s >= NAME_WORD_FLOOR else 0.0

    def covered(these, those):
        total = sum(len(w) for w in these)
        done = sum(len(w) * max((alike(w, o) for o in those), default=0.0) for w in these)
        return done / total if total else 0.0

    if not said or not name:
        return 0.0
    a, b = covered(said, name), covered(name, said)
    return 2 * a * b / (a + b) if a + b else 0.0


def _open_later(ext_id):
    opener = _opener or open_guide
    return lambda: opener(ext_id)


def on_guide_request(request):
    """Aruna's handler for GUIDE_PATTERNS (a core.commands.Request)."""
    from core.commands import Reply
    from core.i18n import get_translator
    _ = get_translator("core")
    kind, ext_id, title, has = match_guide(request.text)
    if kind is None:
        return None
    if not has:
        return Reply(say=_("guide_missing", name=title))
    opening = _("guide_opening", name=title)
    if kind == "run":
        return Reply(say=opening, then=_open_later(ext_id))
    return Reply(say=_("guide_confirm", name=title),
                 confirm=lambda: Reply(say=opening, then=_open_later(ext_id)))


def register_intent(opener=None):
    """Teach Aruna "panduan <extension>" (the main window calls it at
    startup). `opener(ext_id)` opens a guide; default open_guide()."""
    global _opener
    import core.commands
    from core.i18n import get_translator
    _opener = opener
    core.commands.add_intent(GUIDE_INTENT, list(GUIDE_PATTERNS), on_guide_request,
                             title=get_translator("core")("guide_intent_title"))
