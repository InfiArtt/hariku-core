# gcal_integration/dialogs.py
# ============================================================
# Accessible Event Editor Dialog for Hariku V2
# ============================================================
# A wx.Dialog that mirrors Google Calendar's event fields.
# Designed to be 100% NVDA-friendly: every control is reachable
# via Tab, and all labels are associated with their controls.
# ============================================================

import wx
import uuid
import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================
# Recurrence choices (displayed in ComboBox)
# ============================================================

RECURRENCE_CHOICES = [
    ("none",    "Does not repeat"),
    ("daily",   "Daily"),
    ("weekly",  "Weekly"),
    ("monthly", "Monthly"),
    ("yearly",  "Yearly"),
]

RECURRENCE_RRULES = {
    "none":    None,
    "daily":   "FREQ=DAILY",
    "weekly":  "FREQ=WEEKLY",
    "monthly": "FREQ=MONTHLY",
    "yearly":  "FREQ=YEARLY",
}


def _rrule_to_index(rrule_str):
    """Map an RRULE string to the ComboBox index."""
    if not rrule_str:
        return 0
    upper = rrule_str.upper()
    for i, (key, rule) in enumerate(RECURRENCE_RRULES.items()):
        if rule and rule in upper:
            return i
    return 0


# ============================================================
# Status choices
# ============================================================

STATUS_CHOICES = [
    ("confirmed",  "Confirmed"),
    ("tentative",  "Tentative"),
    ("cancelled",  "Cancelled"),
]


# ============================================================
# EventEditorDialog
# ============================================================

class EventEditorDialog(wx.Dialog):
    """
    Full-featured event editor with all Google Calendar fields.

    Can be used in two modes:
      - Create mode: pass event_data=None
      - Edit mode:   pass an existing event dict
    """

    def __init__(self, parent, date_str, event_data=None):
        title = "Edit Event" if event_data else "New Event"
        super().__init__(parent, title=title, size=(500, 580))

        self.date_str = date_str
        self.event_data = event_data
        self.result = None  # Will hold the saved event dict

        self._init_ui()
        self._populate(event_data)
        self.CentreOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ---- Title ----
        vbox.Add(wx.StaticText(panel, label="Title:"), 0, wx.LEFT | wx.TOP, 10)
        self.txt_title = wx.TextCtrl(panel)
        vbox.Add(self.txt_title, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- All Day checkbox ----
        self.chk_all_day = wx.CheckBox(panel, label="All day event")
        self.chk_all_day.Bind(wx.EVT_CHECKBOX, self._on_all_day_toggle)
        vbox.Add(self.chk_all_day, 0, wx.ALL, 10)

        # ---- Start Date ----
        vbox.Add(wx.StaticText(panel, label="Start Date (YYYY-MM-DD):"), 0, wx.LEFT, 10)
        self.txt_start_date = wx.TextCtrl(panel, value=self.date_str)
        vbox.Add(self.txt_start_date, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- Start Time ----
        now = datetime.datetime.now()
        default_time = (now + datetime.timedelta(minutes=1)).strftime("%H:%M")
        self.lbl_start_time = wx.StaticText(panel, label="Start Time (HH:MM):")
        vbox.Add(self.lbl_start_time, 0, wx.LEFT | wx.TOP, 10)
        self.txt_start_time = wx.TextCtrl(panel, value=default_time)
        vbox.Add(self.txt_start_time, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- End Date ----
        vbox.Add(wx.StaticText(panel, label="End Date (YYYY-MM-DD):"), 0, wx.LEFT | wx.TOP, 10)
        self.txt_end_date = wx.TextCtrl(panel, value=self.date_str)
        vbox.Add(self.txt_end_date, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- End Time ----
        end_time = (now + datetime.timedelta(hours=1, minutes=1)).strftime("%H:%M")
        self.lbl_end_time = wx.StaticText(panel, label="End Time (HH:MM):")
        vbox.Add(self.lbl_end_time, 0, wx.LEFT | wx.TOP, 10)
        self.txt_end_time = wx.TextCtrl(panel, value=end_time)
        vbox.Add(self.txt_end_time, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- Location ----
        vbox.Add(wx.StaticText(panel, label="Location:"), 0, wx.LEFT | wx.TOP, 10)
        self.txt_location = wx.TextCtrl(panel)
        vbox.Add(self.txt_location, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- Description ----
        vbox.Add(wx.StaticText(panel, label="Description:"), 0, wx.LEFT | wx.TOP, 10)
        self.txt_description = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 80))
        vbox.Add(self.txt_description, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- Recurrence ----
        vbox.Add(wx.StaticText(panel, label="Repeat:"), 0, wx.LEFT | wx.TOP, 10)
        self.cmb_recurrence = wx.ComboBox(
            panel,
            choices=[label for _, label in RECURRENCE_CHOICES],
            style=wx.CB_READONLY,
        )
        self.cmb_recurrence.SetSelection(0)
        vbox.Add(self.cmb_recurrence, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- Status ----
        vbox.Add(wx.StaticText(panel, label="Status:"), 0, wx.LEFT | wx.TOP, 10)
        self.cmb_status = wx.ComboBox(
            panel,
            choices=[label for _, label in STATUS_CHOICES],
            style=wx.CB_READONLY,
        )
        self.cmb_status.SetSelection(0)
        vbox.Add(self.cmb_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---- Buttons ----
        btn_sizer = wx.StdDialogButtonSizer()
        btn_save = wx.Button(panel, wx.ID_OK, "Save")
        btn_save.SetDefault()
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_sizer.AddButton(btn_save)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)

        btn_save.Bind(wx.EVT_BUTTON, self._on_save)

        # Set initial focus to title field
        self.txt_title.SetFocus()

    def _on_all_day_toggle(self, event):
        """Show/hide time fields based on the All Day checkbox."""
        is_all_day = self.chk_all_day.GetValue()
        self.txt_start_time.Enable(not is_all_day)
        self.txt_end_time.Enable(not is_all_day)
        self.lbl_start_time.Enable(not is_all_day)
        self.lbl_end_time.Enable(not is_all_day)

    def _populate(self, data):
        """Fill the form fields with existing event data (edit mode)."""
        if not data:
            return

        self.txt_title.SetValue(data.get("summary", ""))
        self.txt_location.SetValue(data.get("location", ""))
        self.txt_description.SetValue(data.get("description", ""))

        is_all_day = data.get("all_day", False)
        self.chk_all_day.SetValue(is_all_day)
        self._on_all_day_toggle(None)

        start = data.get("start_time", "")
        end = data.get("end_time", "")

        if start:
            self.txt_start_date.SetValue(start[:10])
            if not is_all_day and len(start) >= 16:
                self.txt_start_time.SetValue(start[11:16])

        if end:
            self.txt_end_date.SetValue(end[:10])
            if not is_all_day and len(end) >= 16:
                self.txt_end_time.SetValue(end[11:16])

        # Recurrence
        rrule = data.get("recurrence")
        self.cmb_recurrence.SetSelection(_rrule_to_index(rrule))

        # Status
        status = data.get("status", "confirmed").lower()
        for i, (key, _) in enumerate(STATUS_CHOICES):
            if key == status:
                self.cmb_status.SetSelection(i)
                break

    def _validate_date(self, value, field_name):
        """Validate a YYYY-MM-DD date string."""
        try:
            datetime.datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            wx.MessageBox(
                f"Invalid {field_name}. Use YYYY-MM-DD format.",
                "Validation Error",
                wx.ICON_ERROR,
            )
            return False

    def _validate_time(self, value, field_name):
        """Validate a HH:MM time string."""
        try:
            datetime.datetime.strptime(value, "%H:%M")
            return True
        except ValueError:
            wx.MessageBox(
                f"Invalid {field_name}. Use HH:MM format (e.g. 14:30).",
                "Validation Error",
                wx.ICON_ERROR,
            )
            return False

    def _on_save(self, event):
        """Validate inputs and build the event dict."""
        title = self.txt_title.GetValue().strip()
        if not title:
            wx.MessageBox("Title cannot be empty.", "Validation Error", wx.ICON_ERROR)
            return

        start_date = self.txt_start_date.GetValue().strip()
        end_date = self.txt_end_date.GetValue().strip()
        if not self._validate_date(start_date, "Start Date"):
            return
        if not self._validate_date(end_date, "End Date"):
            return

        is_all_day = self.chk_all_day.GetValue()

        if is_all_day:
            start_time_str = start_date
            end_time_str = end_date
        else:
            start_time = self.txt_start_time.GetValue().strip()
            end_time = self.txt_end_time.GetValue().strip()
            if not self._validate_time(start_time, "Start Time"):
                return
            if not self._validate_time(end_time, "End Time"):
                return
            start_time_str = f"{start_date}T{start_time}:00"
            end_time_str = f"{end_date}T{end_time}:00"

        # Recurrence
        rec_idx = self.cmb_recurrence.GetSelection()
        rec_key = RECURRENCE_CHOICES[rec_idx][0] if rec_idx >= 0 else "none"
        recurrence = RECURRENCE_RRULES.get(rec_key)

        # Status
        status_idx = self.cmb_status.GetSelection()
        status_key = STATUS_CHOICES[status_idx][0] if status_idx >= 0 else "confirmed"

        # Build the event
        event_id = (
            self.event_data["id"]
            if self.event_data and self.event_data.get("id")
            else f"local-{uuid.uuid4().hex[:12]}"
        )

        self.result = {
            "id": event_id,
            "summary": title,
            "description": self.txt_description.GetValue().strip(),
            "location": self.txt_location.GetValue().strip(),
            "all_day": is_all_day,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "recurrence": recurrence,
            "status": status_key,
            "transparency": "transparent" if is_all_day else "opaque",
            "is_local": True,
        }

        self.EndModal(wx.ID_OK)

    def get_result(self):
        """Return the saved event dict (or None if cancelled)."""
        return self.result
