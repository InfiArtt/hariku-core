# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================
# Internationalization (i18n) Engine for Hariku V2
# ============================================================
# JSON-based translation system. No compilation needed.
# Each language file contains a "manifest" and "messages" block.
# ============================================================

import os
import sys
import json
import logging

logger = logging.getLogger(__name__)

# Global state
_current_language = "en"
_fallback_language = "en"
_language_cache = {}  # domain -> {lang_code -> {manifest: {}, messages: {}}}
_persona = ""         # how Hariku talks (core.persona): "key@persona" is looked up first

# Core locales directory
import builtins as _builtins
if getattr(sys, 'frozen', False) or hasattr(_builtins, '__compiled__') or hasattr(sys, 'nuitka_version'):
    _app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CORE_LOCALES_DIR = os.path.join(_BASE_DIR, "locales")
    # Also check AppData for user-installed language packs
    USER_LOCALES_DIR = os.path.join(_app_data, "Hariku2", "locales")
else:
    CORE_LOCALES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "locales"))
    USER_LOCALES_DIR = None


def init(language_code=None):
    """
    Initialize the i18n system.
    If language_code is None, reads from Core preferences.
    """
    global _current_language
    
    if language_code is None:
        import core.api
        config = core.api.load_data("Core")
        language_code = config.get("language", "en")
    
    _current_language = language_code
    
    # Pre-load core translations
    _load_domain("core", CORE_LOCALES_DIR)
    
    logger.info(f"i18n initialized. Language: {_current_language}")


def get_current_language():
    """Return the currently active language code."""
    return _current_language


def set_language(language_code):
    """
    Change the active language. Requires app restart to take full effect.
    Saves the preference to Core config.
    """
    global _current_language
    _current_language = language_code
    
    import core.api
    config = core.api.load_data("Core")
    config["language"] = language_code
    core.api.save_data("Core", config)
    
    # Clear cache to force reload
    _language_cache.clear()
    _load_domain("core", CORE_LOCALES_DIR)
    
    logger.info(f"Language changed to: {language_code}")


def use_language(language_code):
    """
    Switch the language right away, without saving it and without a restart
    (core 2.10; the welcome dialog does this when the user picks a language).
    Translators look the language up each time they are called, so every text
    made from now on is in it. Unlike set_language(), the translations already
    loaded stay, extensions' included. Returns whether `language_code` is one
    of the core's languages (nothing changes otherwise).
    """
    global _current_language
    if "core" not in _language_cache or not _language_cache["core"]:
        _load_domain("core", CORE_LOCALES_DIR)
    if language_code not in _language_cache.get("core", {}):
        return False
    _current_language = language_code
    return True


def set_persona(persona):
    """Talk in `persona` (core 2.10; core.persona chooses it): from now on a
    text is looked up as "key@persona" first, then as "key". "" for none."""
    global _persona
    _persona = str(persona or "")


def get_persona():
    return _persona


def translations(key, domain="core"):
    """Every language's text for `key` (core 2.10), in no particular order;
    languages without it are left out."""
    found = []
    for lang_data in _language_cache.get(domain, {}).values():
        text = lang_data["messages"].get(key)
        if isinstance(text, str) and text not in found:
            found.append(text)
    return found


def _load_domain(domain, locales_dir):
    """
    Load all available language files for a given domain from a locales directory.
    Each .json file in the directory is treated as a language pack.
    """
    if domain not in _language_cache:
        _language_cache[domain] = {}
    
    if not locales_dir or not os.path.isdir(locales_dir):
        return
    
    for filename in os.listdir(locales_dir):
        if not filename.endswith(".json"):
            continue
        
        filepath = os.path.join(locales_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Validate structure
            if "manifest" not in data or "messages" not in data:
                logger.warning(f"Invalid language file (missing manifest/messages): {filepath}")
                continue
            
            manifest = data["manifest"]
            
            # Validate required manifest fields
            required = ["language_name", "language_code", "translator", "email", "version"]
            missing = [f for f in required if f not in manifest]
            if missing:
                logger.warning(f"Language file '{filepath}' missing manifest fields: {missing}")
                continue
            
            lang_code = manifest["language_code"]
            _language_cache[domain][lang_code] = {
                "manifest": manifest,
                "messages": data["messages"],
                "filepath": filepath
            }
            
            logger.debug(f"Loaded language pack [{domain}]: {manifest['language_name']} ({lang_code})")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse language file {filepath}: {e}")
        except Exception as e:
            logger.error(f"Failed to load language file {filepath}: {e}")
    
    # Also load from user locales directory if available
    if USER_LOCALES_DIR and os.path.isdir(USER_LOCALES_DIR):
        domain_user_dir = os.path.join(USER_LOCALES_DIR, domain)
        if os.path.isdir(domain_user_dir) and domain_user_dir != locales_dir:
            for filename in os.listdir(domain_user_dir):
                if not filename.endswith(".json"):
                    continue
                filepath = os.path.join(domain_user_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "manifest" in data and "messages" in data:
                        lang_code = data["manifest"]["language_code"]
                        # User packs override built-in packs
                        _language_cache[domain][lang_code] = {
                            "manifest": data["manifest"],
                            "messages": data["messages"],
                            "filepath": filepath
                        }
                        logger.info(f"User language pack overrides [{domain}]: {lang_code}")
                except Exception as e:
                    logger.error(f"Failed to load user language file {filepath}: {e}")


def _translate(domain, key, **kwargs):
    """
    Internal translation lookup.
    Tries current language first, then falls back to fallback language,
    then returns the key itself if no translation found. In each language the
    persona's own version ("key@persona") comes before the plain one.
    """
    domain_data = _language_cache.get(domain, {})
    keys = (f"{key}@{_persona}", key) if _persona else (key,)

    # Try current language
    lang_data = domain_data.get(_current_language)
    if lang_data:
        text = next((lang_data["messages"][k] for k in keys if k in lang_data["messages"]), None)
        if text is not None:
            if kwargs:
                try:
                    return text.format(**kwargs)
                except (KeyError, IndexError):
                    return text
            return text

    # Fallback to default language
    if _current_language != _fallback_language:
        fallback_data = domain_data.get(_fallback_language)
        if fallback_data:
            messages = fallback_data["messages"]
            text = next((messages[k] for k in keys if k in messages), None)
            if text is not None:
                if kwargs:
                    try:
                        return text.format(**kwargs)
                    except (KeyError, IndexError):
                        return text
                return text
    
    # Last resort: return the key itself
    return kwargs.get("default", key)


def get_translator(domain, locales_dir=None):
    """
    Returns a translation function _() for a specific domain.
    
    For core usage:
        from core.i18n import get_translator
        _ = get_translator("core")
        print(_("welcome_message"))
    
    For extensions:
        from core.i18n import get_translator
        import os
        EXT_DIR = os.path.dirname(os.path.abspath(__file__))
        _ = get_translator("my_extension", os.path.join(EXT_DIR, "locales"))
        print(_("greeting"))
    
    Supports named placeholders:
        _("hello_name", name="Rafli")
        # en.json: {"hello_name": "Hello, {name}!"}
    """
    # Load domain if not cached and locales_dir provided
    if domain not in _language_cache and locales_dir:
        _load_domain(domain, locales_dir)
    elif domain not in _language_cache:
        _language_cache[domain] = {}
    
    def translator(key, **kwargs):
        return _translate(domain, key, **kwargs)
    
    return translator


def get_available_languages(domain="core"):
    """
    Returns a list of available languages for a domain.
    Each item is a dict with: language_code, language_name, translator, email, version, etc.
    """
    domain_data = _language_cache.get(domain, {})
    languages = []
    
    for lang_code, lang_data in domain_data.items():
        manifest = lang_data["manifest"].copy()
        languages.append(manifest)
    
    # Sort: current language first, then alphabetical
    languages.sort(key=lambda x: (
        0 if x["language_code"] == _current_language else 1,
        x["language_name"]
    ))
    
    return languages


def get_language_manifest(domain="core", language_code=None):
    """
    Returns the manifest dict for a specific language in a domain.
    If language_code is None, returns for the current language.
    """
    if language_code is None:
        language_code = _current_language
    
    domain_data = _language_cache.get(domain, {})
    lang_data = domain_data.get(language_code)
    
    if lang_data:
        return lang_data["manifest"]
    return None

def format_date(date_obj, format_string):
    """
    Format a wx.DateTime or datetime object into a translated string,
    bypassing the OS locale settings.
    Supports %A, %a, %B, %b, %d, %m, %Y
    """
    # Extract components
    if hasattr(date_obj, "GetWeekDay"):  # wx.DateTime
        # wx.DateTime.Mon is 1, Sun is 0. Convert to Python weekday (Mon=0, Sun=6)
        wx_wd = date_obj.GetWeekDay()
        weekday = 6 if wx_wd == 0 else wx_wd - 1
        month = date_obj.GetMonth() + 1 # wx months are 0-11
        day = date_obj.GetDay()
        year = date_obj.GetYear()
    else:  # datetime.date / datetime.datetime
        weekday = date_obj.weekday() # Mon=0, Sun=6
        month = date_obj.month
        day = date_obj.day
        year = date_obj.year
        
    _ = get_translator("core")
    
    res = format_string
    # Full day name
    res = res.replace("%A", _(f"day_{weekday}"))
    # Short day name
    res = res.replace("%a", _(f"day_short_{weekday}"))
    # Full month name
    res = res.replace("%B", _(f"month_{month}"))
    # Short month name
    res = res.replace("%b", _(f"month_short_{month}"))
    
    # Numbers
    res = res.replace("%d", f"{day:02d}")
    res = res.replace("%m", f"{month:02d}")
    res = res.replace("%Y", f"{year:04d}")
    
    return res

def apply_rtl_layout(window):
    """
    Checks the current language manifest. If 'rtl' is true, applies Right-To-Left 
    layout mirroring to the given wx.Window.
    """
    import wx
    manifest = get_language_manifest("core")
    if manifest and manifest.get("rtl", False):
        window.SetLayoutDirection(wx.Layout_RightToLeft)
        # Also ensure child windows inherit it
        for child in window.GetChildren():
            child.SetLayoutDirection(wx.Layout_RightToLeft)
