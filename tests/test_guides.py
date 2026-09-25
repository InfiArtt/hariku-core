# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Guides (core 2.11): the Markdown and text converters (headings, lists,
# escaping, no scripts, the language), finding, listing and opening guides
# with fake extension folders and .hrk files (the English fallback, links and
# paths that lead outside refused, the size limit), every official extension's
# own guides, Aruna's "panduan orbit" next to the other commands with content,
# the Extension Manager's Guide button, and packaging. No browser is opened:
# the page is checked as a string, and opening is a fake.

import ast
import os
import re
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_ROOT = os.path.join(ROOT, "extensions")


@pytest.fixture
def g():
    import core.guides
    return core.guides


# ------------------------------------------------------------
# Markdown to HTML
# ------------------------------------------------------------

def test_headings_and_the_title(g):
    body, title = g.markdown_body("# Orbit\n\n## Getting started\n\n### Moving ###\n#### Deep\n")
    assert title == "Orbit"
    assert body.split("\n") == ["<h1>Orbit</h1>", "<h2>Getting started</h2>",
                                "<h3>Moving</h3>", "<h4>Deep</h4>"]


def test_only_the_first_h1_is_the_title(g):
    body, title = g.markdown_body("Intro first.\n\n# Real title\n\n# Another\n")
    assert title == "Real title"
    assert body.count("<h1>") == 2


def test_not_headings(g):
    body, _title = g.markdown_body("#hashtag is text\n\n    # indented four is text too\n")
    assert "<h" not in body
    assert "#hashtag is text" in body


def test_paragraphs_join_their_lines(g):
    body, _title = g.markdown_body("One line\nand the next.\n\nA new one.")
    assert body == "<p>One line and the next.</p>\n<p>A new one.</p>"


def test_lists(g):
    body, _title = g.markdown_body(
        "- one\n- two\n  goes on\n\n- three after a blank line\n\nText.\n\n"
        "1. first\n2. second\n\n3) third\n\n5. starts at five\n")
    assert body.split("\n") == [
        "<ul>", "<li>one</li>", "<li>two goes on</li>", "<li>three after a blank line</li>",
        "</ul>", "<p>Text.</p>",
        "<ol>", "<li>first</li>", "<li>second</li>", "<li>third</li>", "<li>starts at five</li>",
        "</ol>"]


def test_a_list_after_a_paragraph_and_a_lazy_line(g):
    body, _title = g.markdown_body("Before:\n- a\nlazy line\n* b\n+ c\n")
    assert body.split("\n") == ["<p>Before:</p>", "<ul>", "<li>a lazy line</li>", "<li>b</li>",
                                "<li>c</li>", "</ul>"]


def test_an_ordered_list_that_starts_later(g):
    body, _title = g.markdown_body("4. four\n5. five\n")
    assert body.startswith('<ol start="4">')


def test_code_bold_and_rules(g):
    body, _title = g.markdown_body("Type `help <topic>` **now**, 25 * 4 stays.\n\n---\n\n"
                                   "```\nif a < b:\n    print('&')\n```\n")
    assert body.split("\n") == [
        "<p>Type <code>help &lt;topic&gt;</code> <strong>now</strong>, 25 * 4 stays.</p>",
        "<hr>",
        "<pre><code>if a &lt; b:", "    print(&#x27;&amp;&#x27;)</code></pre>"]


@pytest.mark.parametrize("evil", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '"><script>alert(1)</script>',
    "`</code><script>alert(1)</script>`",
    "**<script>alert(1)</script>**",
    "# <script>alert(1)</script>",
    "- <iframe src=javascript:alert(1)>",
    "[click](javascript:alert(1))",
    "<a href=\"javascript:alert(1)\">x</a>",
    "```\n</pre><script>alert(1)</script>\n```",
])
def test_nothing_in_a_guide_becomes_html(g, evil):
    page = g.markdown_to_html(evil, "en")
    body = page.split("<body>", 1)[1]
    assert "<script" not in page.lower()
    assert "<img" not in body and "<iframe" not in body and "<a " not in body
    # Every tag in the body is one the converter makes; the rest is text.
    tags = set(re.findall(r"<\s*/?\s*([a-zA-Z0-9]+)", body))
    assert tags <= {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li", "code", "pre",
                    "strong", "hr", "body", "html"}, tags


def test_the_page(g):
    page = g.markdown_to_html("# Panduan Orbit\n\nHalo.", "id")
    assert page.startswith("<!DOCTYPE html>\n<html lang=\"id\">")
    assert "<title>Panduan Orbit</title>" in page
    assert '<meta charset="utf-8">' in page
    assert "Content-Security-Policy" in page and "default-src 'none'" in page
    assert "<script" not in page


def test_the_title_is_escaped_once(g):
    page = g.markdown_to_html("# Tom & Jerry <3", "en")
    assert "<title>Tom &amp; Jerry &lt;3</title>" in page
    assert "<h1>Tom &amp; Jerry &lt;3</h1>" in page


def test_a_guide_without_a_title_gets_one(g):
    page = g.markdown_to_html("Just text.", "en", title="Weather")
    assert "<h1>Weather</h1>" in page and "<title>Weather</title>" in page


@pytest.mark.parametrize("lang, expected", [
    ("id", 'lang="id"'), ("pt-BR", 'lang="pt-BR"'), ("pt_BR", 'lang="pt-BR"'),
    ("ar", 'lang="ar" dir="rtl"'), ('en" onload="x', 'lang="en"'), ("", 'lang="en"'),
    (None, 'lang="en"'), ("../../x", 'lang="en"'),
])
def test_the_language(g, lang, expected):
    assert f"<html {expected}>" in g.page("<p>x</p>", "T", lang)


def test_windows_line_endings_and_a_bom(g):
    body, title = g.markdown_body("# T\r\n\r\nA\r\nB\r\n")
    assert title == "T" and "<p>A B</p>" in body
    assert g._decode("\ufeff# T".encode("utf-8")) == "# T"


# ------------------------------------------------------------
# Hariku's own .txt guide to HTML
# ------------------------------------------------------------

TEXT_GUIDE = """================================================================================
HARIKU V2 — USER GUIDE
Version 2
================================================================================

Welcome to Hariku.
Read it once.

================================================================================
1. GETTING STARTED
================================================================================

THE WELCOME
------------
The first time you start Hariku <you> meet it.
  1. Hello.
     Choose your language.
  2. Your name.
Then the main window opens.
"""


def test_text_guide(g):
    body, title = g.text_body(TEXT_GUIDE)
    assert title == "HARIKU V2 — USER GUIDE"
    assert body.split("\n") == [
        "<h1>HARIKU V2 — USER GUIDE</h1>", "<p>Version 2</p>",
        "<p>Welcome to Hariku. Read it once.</p>",
        "<h2>1. GETTING STARTED</h2>",
        "<h3>THE WELCOME</h3>",
        "<p>The first time you start Hariku &lt;you&gt; meet it.</p>",
        "<ol>", "<li>Hello. Choose your language.</li>", "<li>Your name.</li>", "</ol>",
        "<p>Then the main window opens.</p>"]


def test_text_lists_and_tables(g):
    body, _title = g.text_body("Keys:\n  - Menu: Extensions\n  - Keyboard: Ctrl + X\n\n"
                               "  Left Arrow         Move to the previous day\n"
                               "  Right Arrow        Move to the next day\n\n"
                               "  - an item\n  Not an item\n")
    assert body.split("\n") == [
        "<h1>Hariku</h1>", "<p>Keys:</p>", "<ul>", "<li>Menu: Extensions</li>", "<li>Keyboard: Ctrl + X</li>",
        "</ul>",
        "<pre>  Left Arrow         Move to the previous day",
        "  Right Arrow        Move to the next day</pre>",
        "<pre>  - an item", "  Not an item</pre>"]


def test_a_text_guide_without_a_banner(g):
    body, title = g.text_body("Panduan singkat.\n\nIsi.", title="Panduan Pengguna")
    assert title == "Panduan Pengguna"
    assert body.startswith("<h1>Panduan Pengguna</h1>")


@pytest.mark.parametrize("lang, sections", [("en", 15), ("id", 2)])
def test_the_core_guides_convert(g, lang, sections):
    with open(os.path.join(ROOT, "docs", lang, "user_guide.txt"), encoding="utf-8") as f:
        text = f.read()
    body, title = g.text_body(text)
    assert title and body.count("<h1>") == 1
    assert body.count("<h2>") >= sections
    assert "=====" not in body and "<script" not in body
    assert "<h3>" in body and "<ul>" in body


# ------------------------------------------------------------
# Finding, listing, reading and opening (fake installations)
# ------------------------------------------------------------

GUIDES = {"en": "# Weather\n\n## Getting started\n\nPress W.\n",
          "id": "# Cuaca\n\n## Mulai\n\nTekan W.\n"}


def _manifest(name):
    return ('{"name": "%s", "version": "1.0", "author": "Rafli", "description": "d", '
            '"main": "main.py", "language": "en", "minimum_core_version": "2.0"}' % name)


def _folder(base, ext_id, name, guides):
    folder = os.path.join(base, ext_id)
    os.makedirs(folder)
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(_manifest(name))
    for lang, text in guides.items():
        os.makedirs(os.path.join(folder, "docs", lang))
        with open(os.path.join(folder, "docs", lang, "guide.md"), "w", encoding="utf-8") as f:
            f.write(text)
    return folder


def _archive(base, ext_id, name, guides, extra=None):
    path = os.path.join(base, ext_id + ".hrk")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", _manifest(name))
        z.writestr("main.py", "")
        for lang, text in guides.items():
            z.writestr(f"docs/{lang}/guide.md", text)
        for member, text in (extra or {}).items():
            z.writestr(member, text)
    return path


@pytest.fixture
def world(g, tmp_path, monkeypatch):
    """A system folder and a user folder with extensions in them, Hariku in
    Indonesian, and a temp folder of its own; nothing is opened."""
    import core.extension_manager as manager
    from core import i18n
    system, user = tmp_path / "system", tmp_path / "user"
    system.mkdir()
    user.mkdir()
    monkeypatch.setattr(manager, "SYSTEM_EXTENSIONS_DIR", str(system))
    monkeypatch.setattr(manager, "USER_EXTENSIONS_DIR", str(user))
    monkeypatch.setattr(manager, "LOADED_EXTENSIONS", {})
    monkeypatch.setattr(g, "_scratchpad_dir", lambda: None)
    monkeypatch.setattr(i18n, "_current_language", "id")
    monkeypatch.setattr(g.tempfile, "gettempdir", lambda: str(tmp_path / "temp"))
    (tmp_path / "temp").mkdir()
    g._titles.clear()
    g._archive_titles.clear()

    def installed():
        found = []
        for base in (system, user):
            for item in os.listdir(base):
                ext_id = item[:-4] if item.endswith(".hrk") else item
                found.append({"id": ext_id, "name": ext_id.title()})
        return found

    monkeypatch.setattr(manager, "get_installed_extensions_info", installed)
    _folder(str(system), "weather", "Weather", GUIDES)
    _folder(str(system), "space", "Space", {"en": "# Space\n\nThe ISS.\n"})
    _folder(str(system), "plain", "Plain", {})
    _archive(str(user), "orbit", "Orbit", {"en": "# Orbit\n\nPlay.\n",
                                           "id": "# Orbit\n\n## Mulai\n\nMain.\n"})
    return tmp_path


def test_find_in_the_hariku_language(g, world):
    path = g.find_guide("weather")
    assert path.endswith(os.path.join("weather", "docs", "id", "guide.md"))
    assert g.read_guide(path) == GUIDES["id"]


def test_english_is_the_fallback(g, world):
    assert g.find_guide("weather", "de").endswith(os.path.join("docs", "en", "guide.md"))
    assert g.find_guide("space", "id").endswith(os.path.join("space", "docs", "en", "guide.md"))
    assert g.find_guide("weather", "en").endswith(os.path.join("docs", "en", "guide.md"))


def test_no_guide(g, world):
    assert g.find_guide("plain") is None and not g.has_guide("plain")
    assert g.find_guide("not_installed") is None


def test_a_guide_inside_a_hrk(g, world):
    path = g.find_guide("orbit")
    assert path == os.path.join(str(world / "user" / "orbit.hrk"), "docs", "id", "guide.md")
    assert g.read_guide(path).startswith("# Orbit\n\n## Mulai")
    assert g.guide_languages("orbit") == ["en", "id"]
    assert g.has_guide("orbit")


def test_the_loader_order_wins(g, world):
    # A user folder of the same id comes before the .hrk and the system folder.
    _folder(str(world / "user"), "weather", "Weather", {"en": "# Weather (dev)\n"})
    assert g.find_guide("weather").startswith(str(world / "user"))
    assert g.title_of(g.find_guide("weather")) == "Weather (dev)"


@pytest.mark.parametrize("ext_id", ["../system/weather", "..", "weather/../weather", "C:\\x",
                                    "", None, "a" * 65, "we ather"])
def test_ids_that_are_not_names_are_refused(g, world, ext_id):
    assert g.find_guide(ext_id) is None
    assert g.extension_source(ext_id) is None


def test_a_bad_language_is_the_hariku_language(g, world):
    assert g.find_guide("weather", "../../..").endswith(os.path.join("docs", "id", "guide.md"))


def _junction(link, target):
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError):
        pytest.skip("junctions need Windows")


def test_a_docs_folder_leading_outside_is_refused(g, world):
    outside = world / "outside" / "en"
    outside.mkdir(parents=True)
    (outside / "guide.md").write_text("# Stolen\n", encoding="utf-8")
    folder = world / "system" / "sneaky"
    folder.mkdir()
    (folder / "manifest.json").write_text(_manifest("Sneaky"), encoding="utf-8")
    _junction(folder / "docs", world / "outside")
    assert os.path.isfile(folder / "docs" / "en" / "guide.md")       # it is reachable...
    assert g.find_guide("sneaky") is None                            # ...but not a guide
    assert g.guide_languages("sneaky") == []


def test_a_language_folder_leading_outside_is_refused(g, world):
    outside = world / "elsewhere"
    outside.mkdir()
    (outside / "guide.md").write_text("# Stolen\n", encoding="utf-8")
    folder = world / "system" / "sneaky2"
    (folder / "docs").mkdir(parents=True)
    (folder / "manifest.json").write_text(_manifest("Sneaky"), encoding="utf-8")
    _junction(folder / "docs" / "en", outside)
    assert g.find_guide("sneaky2") is None


def test_only_guides_are_read_from_an_archive(g, world):
    hrk = _archive(str(world / "user"), "tricky", "Tricky", {"en": "# T\n"},
                   extra={"secret.txt": "no", "docs/en/other.md": "no"})
    assert g.read_guide(os.path.join(hrk, "secret.txt")) is None
    assert g.read_guide(os.path.join(hrk, "docs", "en", "other.md")) is None
    assert g.read_guide(os.path.join(hrk, "docs", "..", "secret.txt")) is None
    assert g.read_guide(os.path.join(hrk, "docs", "en", "guide.md")) == "# T\n"


def test_a_guide_too_big_is_not_read(g, world, monkeypatch):
    weather, orbit = g.find_guide("weather"), g.find_guide("orbit")
    monkeypatch.setattr(g, "MAX_GUIDE_BYTES", 10)
    assert g.read_guide(weather) is None        # a folder
    assert g.read_guide(orbit) is None          # a .hrk
    assert g.find_guide("weather") is None and g.find_guide("orbit") is None
    assert g.list_guides() == []


def test_a_broken_archive_has_no_guide(g, world):
    (world / "user" / "broken.hrk").write_bytes(b"not a zip")
    assert g.find_guide("broken") is None and g.guide_languages("broken") == []


def test_list_guides(g, world):
    assert g.list_guides() == [("weather", "Cuaca"), ("orbit", "Orbit"), ("space", "Space")]
    assert g.list_guides("en") == [("orbit", "Orbit"), ("space", "Space"), ("weather", "Weather")]


def test_list_guides_counts_extensions_loaded_from_elsewhere(g, world, monkeypatch):
    import core.extension_manager as manager
    scratch = world / "scratch"
    _folder(str(scratch), "notes", "Notes", {"en": "# Notes\n"})
    monkeypatch.setattr(g, "_scratchpad_dir", lambda: str(scratch))
    monkeypatch.setitem(manager.LOADED_EXTENSIONS, "notes", {"manifest": {"name": "Notes"}})
    assert ("notes", "Notes") in g.list_guides()


def test_open_a_guide(g, world):
    opened = []
    assert g.open_guide("weather", launch=opened.append)
    assert len(opened) == 1
    path = opened[0]
    assert os.path.dirname(path) == g.pages_dir() and path.endswith("weather-id.html")
    with open(path, encoding="utf-8") as f:
        page = f.read()
    assert '<html lang="id">' in page and "<h1>Cuaca</h1>" in page and "<h2>Mulai</h2>" in page
    # Again: the same file, replaced.
    assert g.open_guide("weather", launch=opened.append)
    assert opened[1] == path and len(os.listdir(g.pages_dir())) == 1


def test_open_a_guide_in_english(g, world):
    opened = []
    assert g.open_guide("space", launch=opened.append)
    with open(opened[0], encoding="utf-8") as f:
        assert '<html lang="en">' in f.read()          # the language it is written in


def test_open_a_guide_from_a_hrk(g, world):
    opened = []
    assert g.open_guide("orbit", "en", launch=opened.append)
    with open(opened[0], encoding="utf-8") as f:
        assert "<h1>Orbit</h1>" in f.read()


def test_nothing_to_open(g, world):
    opened = []
    assert not g.open_guide("plain", launch=opened.append)
    assert not g.open_guide("../x", launch=opened.append)
    assert opened == []


def test_a_browser_that_fails(g, world):
    def fail(path):
        raise OSError("no application is associated")
    assert not g.open_guide("weather", launch=fail)


def test_only_pages_in_hariku_s_temp_folder_are_opened(g, world):
    opened = []
    elsewhere = world / "page.html"
    elsewhere.write_text("<p>x</p>", encoding="utf-8")
    assert not g.launch_page(str(elsewhere), launch=opened.append)
    os.makedirs(g.pages_dir(), exist_ok=True)
    not_html = os.path.join(g.pages_dir(), "x.exe")
    open(not_html, "w").close()
    assert not g.launch_page(not_html, launch=opened.append)
    assert opened == []


def test_the_core_guide(g, world):
    assert g.find_guide(g.CORE_ID, "id") == os.path.join(ROOT, "docs", "id", "user_guide.txt")
    assert g.find_guide(g.CORE_ID, "de") == os.path.join(ROOT, "docs", "en", "user_guide.txt")
    opened = []
    assert g.open_core_guide("en", launch=opened.append)
    with open(opened[0], encoding="utf-8") as f:
        page = f.read()
    assert '<html lang="en">' in page and page.count("<h1>") == 1 and "<h2>" in page
    assert opened[0].endswith("core-en.html")


def test_the_core_id_is_never_an_extension(g, world):
    _folder(str(world / "system"), "core", "Core", {"en": "# Not the user guide\n"})
    assert all(ext_id != g.CORE_ID for ext_id, _name in g.list_guides())


def test_the_guides_module_needs_no_window():
    with open(os.path.join(ROOT, "core", "guides.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module}
    assert "wx" not in imported and "webbrowser" not in imported


# ------------------------------------------------------------
# The show_guide() fallback and the list window's logic (fakes)
# ------------------------------------------------------------

def test_show_guide_falls_back_to_text(world, monkeypatch):
    import ui.guides_dialog as gd
    shown, spoken = [], []
    monkeypatch.setattr(gd, "_speak", spoken.append)
    assert gd.show_guide(None, "weather", opener=lambda ext_id: False,
                         show_text=lambda parent, title, text: shown.append((title, text)))
    assert shown == [("Cuaca", GUIDES["id"])]
    assert not gd.show_guide(None, "plain", opener=lambda ext_id: False,
                             show_text=lambda *a: shown.append(a))
    assert len(shown) == 1 and len(spoken) == 1


def test_show_guide_opens_in_the_browser_first(world):
    import ui.guides_dialog as gd
    opened = []
    assert gd.show_guide(None, "weather", opener=lambda ext_id: opened.append(ext_id) or True,
                         show_text=lambda *a: pytest.fail("no text window"))
    assert opened == ["weather"]


# ------------------------------------------------------------
# The Extension Manager's Guide button
# ------------------------------------------------------------

def _row(ext_id="weather", installed=True):
    return {"id": ext_id, "installed": installed}


@pytest.mark.parametrize("row, done, has, enabled", [
    (_row(), "", True, True),
    (_row(), "", False, False),
    (_row(), "removed", True, False),
    (_row(), "updated", True, True),
    (_row(installed=False), "", True, False),
    (None, "", True, False),
])
def test_the_guide_button(row, done, has, enabled):
    import core.extension_catalog as catalog
    assert catalog.can_open_guide(row, done, lambda ext_id: has) is enabled


def test_the_guide_button_asks_core_guides(world):
    import core.extension_catalog as catalog
    assert catalog.can_open_guide(_row("weather"))
    assert catalog.can_open_guide(_row("orbit"))
    assert not catalog.can_open_guide(_row("plain"))


def test_the_installed_tab_has_the_guide_button():
    with open(os.path.join(ROOT, "ui", "extension_manager_dialog.py"), encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    buttons = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "BUTTONS")
    assert "guide" in buttons["installed"]
    assert all("guide" not in keys for tab, keys in buttons.items() if tab != "installed")
    assert "def _do_guide(self, row, page):" in source


# ------------------------------------------------------------
# Every official extension has its guides
# ------------------------------------------------------------

def _official_in_repo():
    import core.extension_manager as manager
    return sorted(ext_id for ext_id in manager._OFFICIAL_EXTENSION_IDS
                  if os.path.isfile(os.path.join(EXT_ROOT, ext_id, "manifest.json")))


def test_most_official_extensions_are_in_this_repo():
    assert len(_official_in_repo()) >= 30


@pytest.mark.parametrize("ext_id", _official_in_repo())
@pytest.mark.parametrize("lang", ["en", "id"])
def test_every_official_extension_has_its_guides(g, ext_id, lang):
    path = os.path.join(EXT_ROOT, ext_id, "docs", lang, "guide.md")
    assert os.path.isfile(path), f"{ext_id} has no {lang} guide"
    assert os.path.getsize(path) < g.MAX_GUIDE_BYTES
    with open(path, encoding="utf-8") as f:
        text = f.read()
    first = text.split("\n", 1)[0]
    assert re.match(r"^# \S", first), f"{path}: the first line must be the # title"
    body, title = g.markdown_body(text)
    assert title and body.count("<h1>") == 1, path
    assert "<h2>" in body, f"{path} has no ## sections"


@pytest.mark.parametrize("ext_id", _official_in_repo())
@pytest.mark.parametrize("lang", ["en", "id"])
def test_guides_use_only_what_the_converter_knows(ext_id, lang):
    path = os.path.join(EXT_ROOT, ext_id, "docs", lang, "guide.md")
    if not os.path.isfile(path):
        pytest.skip("no guide (the test above says so)")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    outside_code = re.sub(r"`[^`\n]*`", "", re.sub(r"```.*?```", "", text, flags=re.S))
    problems = []
    for number, line in enumerate(outside_code.split("\n"), 1):
        if line.lstrip().startswith("|"):
            problems.append(f"{number}: a table")
        if re.search(r"\]\((?:https?|mailto|file)?:?", line):
            problems.append(f"{number}: a link")
        if re.search(r"</?[a-zA-Z][^>]*>", line):
            problems.append(f"{number}: an HTML tag")
        if line.startswith(">"):
            problems.append(f"{number}: a block quote")
        if re.match(r"^ {2,}[-*] ", line):
            problems.append(f"{number}: a nested list")
    assert not problems, f"{path}: " + "; ".join(problems)


@pytest.mark.parametrize("ext_id", _official_in_repo())
def test_indonesian_guides_say_kamu(ext_id):
    path = os.path.join(EXT_ROOT, ext_id, "docs", "id", "guide.md")
    if not os.path.isfile(path):
        pytest.skip("no guide (the test above says so)")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # Labels quoted as the window shows them may say "Anda"; the guide itself doesn't.
    prose = re.sub(r"\"[^\"]*\"|“[^”]*”|`[^`]*`", "", text)
    assert not re.search(r"\bAnda\b", prose), f"{path}: use \"kamu\", not \"Anda\""


# ------------------------------------------------------------
# Aruna: "panduan orbit", and nothing else taken
# ------------------------------------------------------------

@pytest.fixture
def repo(g, monkeypatch, tmp_path):
    """The extensions in this repo, installed as system folders, and Hariku
    in Indonesian."""
    import core.extension_manager as manager
    from core import i18n
    monkeypatch.setattr(manager, "SYSTEM_EXTENSIONS_DIR", EXT_ROOT)
    monkeypatch.setattr(manager, "USER_EXTENSIONS_DIR", str(tmp_path))
    monkeypatch.setattr(manager, "LOADED_EXTENSIONS", {})
    monkeypatch.setattr(g, "_scratchpad_dir", lambda: None)
    monkeypatch.setattr(i18n, "_current_language", "id")
    i18n._load_domain("core", i18n.CORE_LOCALES_DIR)
    import json
    folders = {}
    for ext_id in os.listdir(EXT_ROOT):
        manifest = os.path.join(EXT_ROOT, ext_id, "manifest.json")
        if os.path.isfile(manifest):
            with open(manifest, encoding="utf-8") as f:
                folders[ext_id] = json.load(f).get("name") or ext_id
    monkeypatch.setattr(g, "installed_extensions", lambda: dict(folders))
    g._titles.clear()
    g._archive_titles.clear()
    return g


def _literal_patterns(ext, name):
    with open(os.path.join(EXT_ROOT, ext, "main.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return list(ast.literal_eval(node.value))
    raise AssertionError(f"{ext}: {name} not found")


class Aruna:
    """What ui/command_bar.py does with a text, without the window: the
    commands with content in turn (the guides' real handler; the others
    answer "<their id>"), then Hariku's own commands."""

    def __init__(self, g):
        import core.commands as c
        for folder in ("timer_alarm", "calculator"):
            path = os.path.join(EXT_ROOT, folder)
            if path not in sys.path:
                sys.path.insert(0, path)
        import calculator_intents
        import timer_alarm_intents
        self.c = c

        def owner(intent_id):
            return lambda request: f"<{intent_id}>"

        self.guide = c.Intent(g.GUIDE_INTENT, g.GUIDE_PATTERNS, g.on_guide_request)
        self.intents = [self.guide]
        for name, patterns in timer_alarm_intents.PATTERNS.items():
            if name != "fix":
                self.intents.append(c.Intent(f"Timer and Alarm.{name}", patterns,
                                             owner(f"Timer and Alarm.{name}")))
        for ext, names in (("orbit", ["PLAY_PATTERNS"]), ("dropbox", ["LINK_PATTERNS"]),
                           ("world_trip", ["TRIP_PATTERNS", "ABOUT_PATTERNS", "WHERE_PATTERNS"])):
            for name in names:
                intent_id = f"{ext}.{name[:-9].lower()}"
                self.intents.append(c.Intent(intent_id, _literal_patterns(ext, name),
                                             owner(intent_id)))
        calculator = calculator_intents.Calculator(language=lambda: "id")
        self.intents.append(c.Intent("Calculator.calculate", [], owner("Calculator.calculate"),
                                     matcher=calculator.matcher))
        self.commands = [c.Command(aid, aid, aliases) for aid, aliases in c.BUILTIN_ALIASES.items()]

    def send(self, text):
        """(who answered, the Reply or None)."""
        c = self.c
        for found in c.match_intents(text, self.intents):
            reply = c.Reply.of(found.intent.handler(c.Request(found.text, text, "typed",
                                                              found.intent.id)))
            if reply is not None:
                return found.intent.id, reply
        decided = c._decide_without_intents(text, None, self.commands)
        return (decided.action_id if decided.kind == "run" else decided.kind), None


@pytest.fixture
def aruna(repo):
    return Aruna(repo)


@pytest.mark.parametrize("text, ext_id", [
    ("panduan orbit", "orbit"), ("cara pakai dropbox", "dropbox"),
    ("bantuan kalkulator", "calculator"), ("guide for orbit", "orbit"),
    ("how to use dropbox", "dropbox"), ("Panduan Orbit.", "orbit"),
    ("tolong panduan orbit", "orbit"), ("buka panduan orbit", "orbit"),
    ("bantuan orbit", "orbit"), ("panduan timer", "timer_alarm"),
    ("cara menggunakan alarm", "timer_alarm"), ("help with the calculator", "calculator"),
    ("how do i use voice control", "voice_control"), ("guide to world trip", "world_trip"),
    ("panduan flight radar", "flight_radar"), ("panduan clipboard history", "clipboard_history"),
    ("bantuan untuk dropbox", "dropbox"), ("panduan kalkulator dan konversi", "calculator"),
])
def test_aruna_opens_guides(aruna, text, ext_id):
    opened = []
    aruna.c  # noqa
    import core.guides
    core.guides._opener = opened.append
    try:
        who, reply = aruna.send(text)
        assert who == "Hariku Core.guide", (text, who)
        if reply.confirm is not None:        # a close match is asked about first
            reply = reply.confirm()
        assert reply.then is not None, (text, reply)
        reply.then()
        assert opened == [ext_id], (text, opened)
    finally:
        core.guides._opener = None


@pytest.mark.parametrize("text", ["panduan hariku", "panduan pengguna", "how to use hariku",
                                  "cara pakai aplikasi ini"])
def test_aruna_opens_the_user_guide(aruna, text):
    import core.guides
    opened = []
    core.guides._opener = opened.append
    try:
        who, reply = aruna.send(text)
        assert who == "Hariku Core.guide" and reply.confirm is None
        reply.then()
        assert opened == [core.guides.CORE_ID]
    finally:
        core.guides._opener = None


def test_aruna_says_when_there_is_no_guide(aruna, repo, monkeypatch):
    monkeypatch.setattr(repo, "guide_titles", lambda ext_id: {})
    who, reply = aruna.send("panduan orbit")
    assert who == "Hariku Core.guide"
    assert reply.then is None and reply.confirm is None and "Orbit" in reply.say


@pytest.mark.parametrize("text", [
    # Orbit's own in-game help, through Aruna
    "orbit bantuan", "orbit bantuan kasino", "orbit help", "orbit bantuan bergerak",
    "orbit panduan", "orbit cara pakai kapal",
    # not a guide of anything installed
    "bantuan bergerak", "bantuan kerja", "cara pakai sumpit", "help with my homework",
    "panduan memasak", "how to use chopsticks",
    # the others' commands with content
    "timer 10 menit", "alarm besok jam 5 pagi", "take me to Tokyo", "bawa aku ke Paris",
    "tell me about Jakarta", "di mana aku", "salin link laporan", "copy link",
    "orbit pergi ke kantin", "buka orbit", "25 x 4", "berapa 25 kali 4", "5 km ke mil",
    "2 foot in inches", "lempar koin",
    # Hariku's own
    "jam berapa", "what time is it", "cuaca", "gempa terbaru", "buka pengaturan",
    "tambah pengingat", "panduan ekstensi", "extension guides", "kelola ekstensi",
])
def test_aruna_leaves_other_sentences_alone(aruna, text):
    who, _reply = aruna.send(text)
    assert who != "Hariku Core.guide", (text, who)


@pytest.mark.parametrize("text, owner", [
    ("orbit bantuan", "orbit.play"), ("orbit help", "orbit.play"),
    ("timer 10 menit", "Timer and Alarm.timer"), ("take me to Tokyo", "world_trip.trip"),
    ("salin link laporan", "dropbox.link"), ("25 x 4", "Calculator.calculate"),
    ("panduan ekstensi", "Hariku Core.extension_guides"),
    ("extension guides", "Hariku Core.extension_guides"),
    ("panduan pengguna", "Hariku Core.guide"), ("user guide", "Hariku Core.user_guide"),
    ("jam berapa", "Hariku Core.speak_time"),
])
def test_aruna_still_finds_their_owners(aruna, text, owner):
    assert aruna.send(text)[0] == owner


def test_orbit_s_help_never_matches_the_guide_patterns(aruna):
    found = aruna.c.match_intents("orbit bantuan", aruna.intents)
    assert [m.intent.id for m in found] == ["orbit.play"]
    assert found[0].text == "bantuan"


def test_the_guide_patterns_are_valid(g):
    import core.commands
    intent = core.commands.Intent(g.GUIDE_INTENT, g.GUIDE_PATTERNS, lambda r: None)
    assert len(intent.patterns) == len(set(g.GUIDE_PATTERNS)) >= 8


def test_registering_the_intent(g, monkeypatch):
    import core.commands
    monkeypatch.setattr(core.commands, "_intents", {})
    opened = []
    g.register_intent(opener=opened.append)
    try:
        assert [i.id for i in core.commands.intents()] == [g.GUIDE_INTENT]
        g._open_later("orbit")()
        assert opened == ["orbit"]
    finally:
        g._opener = None


def test_the_main_window_registers_guides():
    with open(os.path.join(ROOT, "ui", "main_window.py"), encoding="utf-8") as f:
        source = f.read()
    assert 'register_action("Hariku Core", "user_guide"' in source
    assert 'register_action("Hariku Core", "extension_guides"' in source
    assert "core.guides.register_intent(" in source
    assert '_("menu_help_ext_guides")' in source


# ------------------------------------------------------------
# Packaging keeps docs/
# ------------------------------------------------------------

def test_the_packager_keeps_guides(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import packager
    finally:
        sys.path.remove(os.path.join(ROOT, "tools"))
    folder = tmp_path / "notes"
    (folder / "docs" / "en").mkdir(parents=True)
    (folder / "docs" / "id").mkdir(parents=True)
    (folder / "manifest.json").write_text(_manifest("Notes"), encoding="utf-8")
    (folder / "main.py").write_text("", encoding="utf-8")
    (folder / "docs" / "en" / "guide.md").write_text("# Notes\n", encoding="utf-8")
    (folder / "docs" / "id" / "guide.md").write_text("# Catatan\n", encoding="utf-8")
    out = tmp_path / "out"
    assert packager.package_extension(str(folder), str(out))
    with zipfile.ZipFile(out / "notes.hrk") as z:
        names = set(z.namelist())
    assert {"docs/en/guide.md", "docs/id/guide.md", "manifest.json", "main.py"} <= names
