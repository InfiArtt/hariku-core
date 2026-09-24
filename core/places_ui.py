# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Windows for Places (core 2.8, see core.places):
  * PlacesPanel  - the Preferences page: the places (Name, Where) with Add,
                   Edit, Remove and Make main, and which place is the main one.
                   Saved on OK or Apply, like the other pages.
  * PlaceDialog  - adds or edits one place: its name, then where it is (an
                   address search, a city search, or pasted coordinates or a
                   map link), and the chosen point in words.
  * PlaceChoice  - the labelled "Place:" list an extension's settings page
                   shows: the main place, every saved place and, when the
                   extension has one, "Its own place…".

Every label is created right before the control it names (screen readers
name a control after the static text created just before it). Selecting in a
list never moves focus; focus only moves after the user asks for something
(a search whose results arrive while they wait on its field or button, a
dialog closing). Network requests run on worker threads and come back through
wx.CallAfter.
"""

import logging
import threading

import wx

import core.place_search as search
import core.places
import core.ui_scale
from core.core_panels import _ScrollingPage, _announce, _labeled, _plain_label, _speak
from core.i18n import get_current_language, get_translator

_ = get_translator("core")
logger = logging.getLogger(__name__)

ADDRESS_MIN_LENGTH = 3
CITY_MIN_LENGTH = 2


def _language():
    return "id" if get_current_language() == "id" else "en"


def _start(target, *args):
    threading.Thread(target=target, args=args, daemon=True, name="hariku-places").start()


# Worker threads: the network only, results back on the UI thread.

def _address_worker(done, search_id, query, language):
    try:
        found, error = search.search_addresses(query, language), None
    except search.LocationError as e:
        found, error = [], e.kind
    except Exception:
        logger.exception("[Places] Address search failed")
        found, error = [], "address_failed"
    wx.CallAfter(done, search_id, query, found, error)


def _city_worker(done, search_id, query, language):
    try:
        found, error = search.search_cities(query, language), None
    except search.LocationError as e:
        found, error = [], e.kind
    except Exception:
        logger.exception("[Places] City search failed")
        found, error = [], "city_failed"
    wx.CallAfter(done, search_id, query, found, error)


def _link_worker(done, link_id, url):
    point, error = None, None
    try:
        point = search.resolve_short_link(url)
    except search.LocationError as e:
        error = e.kind
    except Exception:
        logger.exception("[Places] Short link failed")
        error = "link_failed"
    wx.CallAfter(done, link_id, point, error)


def error_text(kind):
    """What went wrong finding a place, in the user's language."""
    return _("places_find_err_" + kind) if kind in (
        "empty", "not_found", "out_of_range", "zero", "link_no_coordinates", "link_failed",
        "address_failed", "address_busy", "city_failed") else _("places_find_err_not_found")


def candidate_where(found):
    """A search result or pasted point in words (see core.places.where_text)."""
    return core.places.where_text({"lat": found["latitude"], "lon": found["longitude"],
                                   "label": found.get("label") or ""})


def _as_candidate(place):
    return search.candidate(place["lat"], place["lon"], place.get("source"), name=place["name"],
                            label=place.get("label"), timezone=place.get("timezone"),
                            city=place.get("city"), region=place.get("region"),
                            country=place.get("country"))


def _search_row(sizer, parent, label, button_label, make):
    """A label, then a text field with a button beside it."""
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
    row = wx.BoxSizer(wx.HORIZONTAL)
    field = make()
    field.SetName(_plain_label(label))
    row.Add(field, 1, wx.RIGHT, 6)
    button = wx.Button(parent, label=button_label)
    row.Add(button, 0)
    sizer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
    return field, button


def _results_list(sizer, parent, label):
    """The label (kept, so its text can say how many were found), then its list."""
    static = wx.StaticText(parent, label=label)
    sizer.Add(static, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
    listbox = wx.ListBox(parent, size=(-1, 80), style=wx.LB_SINGLE)
    listbox.SetName(_plain_label(label))
    sizer.Add(listbox, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
    return static, listbox


# ------------------------------------------------------------
# Add or edit a place
# ------------------------------------------------------------

class PlaceDialog(wx.Dialog):
    """`result` is the checked place (not saved yet) after OK. Where the place
    is comes from what the user chose last: an address or city result (the
    one selected in its list) or pasted coordinates."""

    def __init__(self, parent, title, place=None, taken=()):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.result = None
        self._place = dict(place) if place else None
        self._taken = list(taken)
        self._found = _as_candidate(place) if place else None
        self._addresses, self._cities = [], []
        self._address_id = self._city_id = self._link_id = 0

        root = wx.BoxSizer(wx.VERTICAL)
        self.txt_name = _labeled(self, root, _("places_lbl_name"), lambda: wx.TextCtrl(
            self, value=place["name"] if place else ""))
        self.txt_name.SetMaxLength(core.places.MAX_NAME_LENGTH)

        self.txt_address, self.btn_address = _search_row(
            root, self, _("places_lbl_address"), _("places_btn_address"),
            lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))
        self.lbl_addresses, self.list_addresses = _results_list(root, self,
                                                                _("places_lbl_addresses"))

        self.txt_city, self.btn_city = _search_row(
            root, self, _("places_lbl_city"), _("places_btn_city"),
            lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))
        self.lbl_cities, self.list_cities = _results_list(root, self, _("places_lbl_cities"))

        self.txt_coords, self.btn_use = _search_row(
            root, self, _("places_lbl_coords"), _("places_btn_use"),
            lambda: wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER))

        self.txt_point = _labeled(self, root, _("places_lbl_point"), lambda: wx.TextCtrl(
            self, style=wx.TE_READONLY))
        self.lbl_error = wx.StaticText(self, label="")
        root.Add(self.lbl_error, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        note = wx.StaticText(self, label=_("places_dialog_note"))
        note.Wrap(520)
        root.Add(note, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        buttons = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(self, wx.ID_OK, _("prefs_btn_ok"))
        self.btn_ok.SetDefault()
        buttons.AddButton(self.btn_ok)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, _("prefs_btn_cancel")))
        buttons.Realize()
        root.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(root)
        self.SetEscapeId(wx.ID_CANCEL)

        self.btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)
        self.txt_address.Bind(wx.EVT_TEXT_ENTER, self._on_address_search)
        self.btn_address.Bind(wx.EVT_BUTTON, self._on_address_search)
        self.list_addresses.Bind(wx.EVT_LISTBOX, self._on_address_selected)
        self.txt_city.Bind(wx.EVT_TEXT_ENTER, self._on_city_search)
        self.btn_city.Bind(wx.EVT_BUTTON, self._on_city_search)
        self.list_cities.Bind(wx.EVT_LISTBOX, self._on_city_selected)
        self.txt_coords.Bind(wx.EVT_TEXT_ENTER, self._on_use)
        self.btn_use.Bind(wx.EVT_BUTTON, self._on_use)
        self._show_point()

        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        core.ui_scale.apply_appearance(self)
        self.Fit()
        width, height = self.GetSize()
        self.SetMinSize((width, height))
        self.SetSize((max(width, 560), height))
        self.CentreOnParent()
        self.txt_name.SetFocus()
        self.txt_name.SelectAll()

    # --- the chosen point ---------------------------------------------------

    def chosen(self):
        """The candidate OK would save, or None."""
        return dict(self._found) if self._found else None

    def _choose(self, found):
        self._found = dict(found)
        self._show_point()

    def _show_point(self):
        self.txt_point.ChangeValue(candidate_where(self._found) if self._found
                                   else _("places_point_none"))

    def _say(self, message):
        speak_now(message)

    # --- address search (Nominatim) ------------------------------------------

    def _on_address_search(self, event=None):
        # Only on Enter or the button: Nominatim forbids search-as-you-type.
        query = " ".join(self.txt_address.GetValue().split())
        if len(query) < ADDRESS_MIN_LENGTH:
            self._say(_("places_address_too_short", count=ADDRESS_MIN_LENGTH))
            return
        self._address_id += 1
        self._say(_("places_address_searching", query=query))
        _start(_address_worker, self._on_addresses, self._address_id, query, _language())

    def _on_addresses(self, search_id, query, found, error):
        if not self or search_id != self._address_id:
            return  # closed, or a newer search is running
        if error:
            self._say(error_text(error))
            return
        self._addresses = found
        self._fill(self.lbl_addresses, self.list_addresses, [f["label"] for f in found],
                   _("places_lbl_addresses_count", count=len(found)),
                   _("places_lbl_addresses_none"))
        if not found:
            self._say(_("places_address_none", query=query))
            return
        self._choose(found[0])
        # The user pressed Search and is still waiting there: take them to the results.
        if wx.Window.FindFocus() in (self.txt_address, self.btn_address):
            self.list_addresses.SetFocus()
        else:
            self._say(_("places_address_found", count=len(found)))

    def _on_address_selected(self, event):
        sel = self.list_addresses.GetSelection()
        if 0 <= sel < len(self._addresses):
            self._choose(self._addresses[sel])   # state only; focus stays in the list
        event.Skip()

    # --- city search (Open-Meteo) --------------------------------------------

    def _on_city_search(self, event=None):
        query = " ".join(self.txt_city.GetValue().split())
        if len(query) < CITY_MIN_LENGTH:
            self._say(_("places_city_too_short", count=CITY_MIN_LENGTH))
            return
        self._city_id += 1
        self._say(_("places_city_searching", query=query))
        _start(_city_worker, self._on_cities, self._city_id, query, _language())

    def _on_cities(self, search_id, query, found, error):
        if not self or search_id != self._city_id:
            return
        if error:
            self._say(error_text(error))
            return
        self._cities = found
        self._fill(self.lbl_cities, self.list_cities, [f["label"] for f in found],
                   _("places_lbl_cities_count", count=len(found)),
                   _("places_lbl_cities_none"))
        if not found:
            self._say(_("places_city_none", query=query))
            return
        self._choose(found[0])
        if wx.Window.FindFocus() in (self.txt_city, self.btn_city):
            self.list_cities.SetFocus()
        else:
            self._say(_("places_city_found", count=len(found)))

    def _on_city_selected(self, event):
        sel = self.list_cities.GetSelection()
        if 0 <= sel < len(self._cities):
            self._choose(self._cities[sel])
        event.Skip()

    def _fill(self, static, listbox, rows, label_count, label_none):
        listbox.Set(rows)
        static.SetLabel(label_count if rows else label_none)
        if rows:
            listbox.SetSelection(0)
        self.Layout()

    # --- coordinates and map links -------------------------------------------

    def _on_use(self, event=None):
        try:
            found = search.parse_location_text(self.txt_coords.GetValue())
        except search.LocationError as e:
            self._say(error_text(e.kind))
            return
        if found["kind"] == "short_link":
            self._link_id += 1
            self._say(_("places_link_expanding"))
            _start(_link_worker, self._on_link, self._link_id, found["url"])
            return
        self._use_point(found["latitude"], found["longitude"])

    def _on_link(self, link_id, point, error):
        if not self or link_id != self._link_id:
            return
        if error:
            self._say(error_text(error))
            return
        self._use_point(*point)

    def _use_point(self, latitude, longitude):
        self._choose(search.candidate(latitude, longitude, "coordinates"))
        self._say(_("places_point_found", point=core.places.point_text(latitude, longitude)))

    # --- OK ------------------------------------------------------------------

    def accept(self):
        """Check the input; True and `result` set when it can be saved,
        otherwise the problem is shown and spoken and focus goes to the field
        to fix."""
        try:
            name = core.places.check_name(self.txt_name.GetValue(), self._taken)
        except core.places.PlaceError as e:
            self._show_error(str(e), self.txt_name)
            return False
        if not self._found:
            self._show_error(_("places_err_no_point"), self.txt_address)
            return False
        try:
            self.result = core.places.place_from_candidate(
                self._found, name, self._place["id"] if self._place else None)
        except core.places.PlaceError as e:
            self._show_error(str(e), self.txt_coords)
            return False
        return True

    def _on_ok(self, event=None):
        if self.accept():
            self.EndModal(wx.ID_OK)

    def _show_error(self, message, ctrl):
        width = self.GetSize().width
        self.lbl_error.SetLabel(message)
        self.lbl_error.Wrap(max(200, self.GetClientSize().width - 20))
        self.Fit()   # room for the message, keeping the width the user gave it
        self.SetSize((max(width, self.GetSize().width), self.GetSize().height))
        self.Layout()
        ctrl.SetFocus()
        if isinstance(ctrl, wx.TextCtrl):
            ctrl.SelectAll()
        # After the focus move, so the reader's announcement of the field doesn't swallow it.
        wx.CallLater(100, _speak, message, True)


def speak_now(message):
    _speak(message, True)


def ask_place(parent, title, place=None, taken=()):
    """Show the place dialog; the checked place, or None if cancelled."""
    dlg = PlaceDialog(parent, title, place, taken)
    try:
        return dlg.result if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()


# ------------------------------------------------------------
# The Preferences page
# ------------------------------------------------------------

class PlacesPanel(_ScrollingPage):
    def __init__(self, parent):
        super().__init__(parent)
        self._load()
        vbox = wx.BoxSizer(wx.VERTICAL)

        lbl_help = wx.StaticText(self, label=_("places_help"))
        lbl_help.Wrap(500)
        vbox.Add(lbl_help, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.list_places = _labeled(
            self, vbox, _("places_lbl_list"),
            lambda: wx.ListCtrl(self, size=(-1, 130),
                                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN),
            proportion=1)
        self.list_places.SetMinSize((-1, 130))
        self.list_places.InsertColumn(0, _("places_col_name"), width=180)
        self.list_places.InsertColumn(1, _("places_col_where"), width=360)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add = wx.Button(self, label=_("places_btn_add"))
        self.btn_edit = wx.Button(self, label=_("places_btn_edit"))
        self.btn_remove = wx.Button(self, label=_("places_btn_remove"))
        self.btn_main = wx.Button(self, label=_("places_btn_main"))
        for btn, handler in ((self.btn_add, self.on_add), (self.btn_edit, self.on_edit),
                             (self.btn_remove, self.on_remove), (self.btn_main, self.on_make_main)):
            btn.Bind(wx.EVT_BUTTON, handler)
            hbox.Add(btn, 0, wx.RIGHT, 5)
        vbox.Add(hbox, 0, wx.ALL, 10)

        self.txt_main = _labeled(self, vbox, _("places_lbl_main"),
                                 lambda: wx.TextCtrl(self, style=wx.TE_READONLY))
        lbl_privacy = wx.StaticText(self, label=_("places_privacy"))
        lbl_privacy.Wrap(500)
        vbox.Add(lbl_privacy, 0, wx.ALL, 10)
        self.SetSizer(vbox)
        if hasattr(self, "SetScrollRate"):
            self.SetScrollRate(0, 20)
            core.ui_scale.apply_appearance(self)
            self.FitInside()   # after scaling, so large text can still be scrolled to

        # Enter edits and Delete removes; selecting a row never moves focus.
        self.list_places.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self._refresh(0)

    # --- data -> controls ----------------------------------------------------

    def _load(self):
        """The saved places, edited here until OK or Apply."""
        self._places = core.places.get_places()
        self._main_id = core.places.get_main_id()
        self._loaded = ([dict(p) for p in self._places], self._main_id)

    def places(self):
        return [dict(p) for p in self._places]

    def main_id(self):
        return self._main_id if any(p["id"] == self._main_id for p in self._places) else (
            self._places[0]["id"] if self._places else None)

    def _main(self):
        main_id = self.main_id()
        return next((p for p in self._places if p["id"] == main_id), None)

    def _row_name(self, place):
        return (_("places_row_main", name=place["name"]) if place["id"] == self.main_id()
                else place["name"])

    def _refresh(self, select=None):
        self.list_places.DeleteAllItems()
        for i, place in enumerate(self._places):
            self.list_places.InsertItem(i, self._row_name(place))
            self.list_places.SetItem(i, 1, core.places.where_text(place))
        if self._places and select is not None:
            select = max(0, min(select, len(self._places) - 1))
            state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
            self.list_places.SetItemState(select, state, state)
            self.list_places.EnsureVisible(select)
        main = self._main()
        self.txt_main.ChangeValue(core.places.describe(main) if main else _("places_main_none"))

    def selected_index(self):
        index = self.list_places.GetFirstSelected()
        return index if 0 <= index < len(self._places) else -1

    def _mark_dirty(self):
        top = wx.GetTopLevelParent(self)
        if top is not None and hasattr(top, "is_dirty"):
            top.is_dirty = True

    def _changed(self, index, message, focus_list=True):
        self._refresh(index)
        self._mark_dirty()
        if focus_list:
            if self._places:
                self.list_places.SetFocus()
            else:
                self.btn_add.SetFocus()
        _announce(message)

    def _on_char_hook(self, event):
        if wx.Window.FindFocus() is self.list_places and not event.HasAnyModifiers():
            code = event.GetKeyCode()
            if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self.on_edit()
                return
            if code in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
                self.on_remove()
                return
        event.Skip()

    # --- actions (replaced in checks: _ask, _confirm) ------------------------

    def _ask(self, title, place=None, taken=()):
        return ask_place(self, title, place, taken)

    def _confirm(self, message):
        dlg = wx.MessageDialog(self, message, _("places_remove_title"),
                               wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        try:
            return dlg.ShowModal() == wx.ID_YES
        finally:
            dlg.Destroy()

    def _taken(self, skip=None):
        return [p["name"] for i, p in enumerate(self._places) if i != skip]

    def on_add(self, event=None):
        if len(self._places) >= core.places.MAX_PLACES:
            _speak(_("places_err_too_many", count=core.places.MAX_PLACES), True)
            return
        place = self._ask(_("places_dlg_add_title"), None, self._taken())
        if place is None:
            return
        place["id"] = core.places.new_id({p["id"] for p in self._places})
        self._places.append(place)
        if len(self._places) == 1:
            self._main_id = place["id"]
            message = _("places_added_main", name=place["name"])
        else:
            message = _("places_added", name=place["name"])
        self._changed(len(self._places) - 1, message)

    def on_edit(self, event=None):
        index = self.selected_index()
        if index < 0:
            _speak(_("places_nothing_selected"), True)
            return
        place = self._ask(_("places_dlg_edit_title"), self._places[index], self._taken(index))
        if place is None:
            return
        place["id"] = self._places[index]["id"]
        self._places[index] = place
        self._changed(index, _("places_changed", name=place["name"]))

    def on_remove(self, event=None):
        index = self.selected_index()
        if index < 0:
            _speak(_("places_nothing_selected"), True)
            return
        place = self._places[index]
        was_main = place["id"] == self.main_id()
        if not self._confirm(_("places_remove_confirm", name=place["name"])):
            return
        self._places.pop(index)
        message = _("places_removed", name=place["name"])
        if was_main and self._places:
            self._main_id = self._places[0]["id"]
            message = " ".join((message, _("places_now_main", name=self._places[0]["name"])))
        elif not self._places:
            self._main_id = None
        self._changed(index, message)

    def on_make_main(self, event=None):
        index = self.selected_index()
        if index < 0:
            _speak(_("places_nothing_selected"), True)
            return
        place = self._places[index]
        if place["id"] == self.main_id():
            _speak(_("places_already_main", name=place["name"]), True)
            return
        self._main_id = place["id"]
        # The button was pressed: focus stays on it.
        self._changed(index, _("places_now_main", name=place["name"]), focus_list=False)

    # --- saving -----------------------------------------------------------------

    def is_changed(self):
        return (self.places(), self.main_id()) != self._loaded

    def ApplyChanges(self):
        if not self.is_changed():
            return
        try:
            saved = core.places.set_places(self._places, self.main_id())
        except core.places.PlaceError as e:
            wx.MessageBox(str(e), _("error"), wx.OK | wx.ICON_ERROR, self)
            return
        self._places = saved
        self._main_id = core.places.get_main_id()
        self._loaded = (self.places(), self._main_id)


_panel_instance = None


def create_places_panel(parent):
    global _panel_instance
    _panel_instance = PlacesPanel(parent)
    return _panel_instance


def apply_places_settings():
    if _panel_instance:
        try:
            _panel_instance.ApplyChanges()
        except RuntimeError:
            pass  # panel already destroyed


# ------------------------------------------------------------
# An extension's "Place:" list
# ------------------------------------------------------------

class PlaceChoice:
    """The labelled "Place:" choice on an extension's settings page. Items:
    the main place ("main"), every saved place (its id) and, with `own`,
    "Its own place…" ("own"). `on_change(key)` runs when the user picks
    another item (focus stays on the list). Call refresh() on
    "on_places_changed"; it keeps the chosen item (a removed place becomes
    the main place)."""

    def __init__(self, parent, sizer, choice=None, own=True, on_change=None, label=None,
                 border=10):
        self._own = own
        self._on_change = on_change
        label = label or _("places_lbl_choice")
        sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, border)
        self._entries = core.places.choice_entries(own)
        self.ctrl = wx.Choice(parent, choices=[text for _key, text in self._entries])
        self.ctrl.SetName(_plain_label(label))
        sizer.Add(self.ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, border)
        self.set_key(choice)
        self.ctrl.Bind(wx.EVT_CHOICE, self._on_choice)

    def _index(self, key):
        key = core.places.normalize_choice(key) or core.places.CHOICE_MAIN
        for index, (entry_key, _text) in enumerate(self._entries):
            if entry_key == key:
                return index
        return 0   # a removed place, or "own" without one: the main place

    def set_key(self, key):
        self.ctrl.SetSelection(self._index(key))

    def key(self):
        index = self.ctrl.GetSelection()
        return self._entries[index][0] if 0 <= index < len(self._entries) \
            else core.places.CHOICE_MAIN

    def is_own(self):
        return self.key() == core.places.CHOICE_OWN

    def refresh(self):
        """The places again (after "on_places_changed"), keeping the choice."""
        key = self.key()
        entries = core.places.choice_entries(self._own)
        if entries != self._entries:
            self._entries = entries
            self.ctrl.Set([text for _key, text in entries])
        self.set_key(key)

    def _on_choice(self, event):
        if self._on_change is not None:
            self._on_change(self.key())
        event.Skip()   # Preferences marks itself changed
