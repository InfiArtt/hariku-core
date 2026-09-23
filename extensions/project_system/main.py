# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import os
import uuid
import datetime
import core.api
from core.events import bus
from core.speech import speak
from core.sounds import play_internal_sound
from core.i18n import get_translator
import core.hotkeys

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
_ = get_translator("project_system", os.path.join(EXT_DIR, "locales"))

def load_projects():
    data = core.api.load_data("project_system")
    return data.get("projects", [])

def save_projects(projects):
    data = core.api.load_data("project_system")
    data["projects"] = projects
    core.api.save_data("project_system", data)

def calculate_progress(project):
    tasks = project.get("tasks", [])
    if not tasks:
        return 0
    done_tasks = sum(1 for t in tasks if t.get("is_done", False))
    return int((done_tasks / len(tasks)) * 100)

def on_date_changed(date_str):
    projects = load_projects()
    due_tasks = []
    
    for p in projects:
        if not p.get("is_completed", False):
            for t in p.get("tasks", []):
                if not t.get("is_done", False) and t.get("deadline_date") == date_str:
                    due_tasks.append((p, t))
    
    if due_tasks:
        count = len(due_tasks)
        if count == 1:
            msg = _("announce_due_tasks", count=count)
        else:
            msg = _("announce_due_tasks_plural", count=count)
            
        speak(msg)
        
        for p, t in due_tasks[:3]:
            speak(_("announce_task_item", task_name=t["name"], project_name=p["name"]))

class TaskManagerDialog(wx.Dialog):
    def __init__(self, parent, project):
        super().__init__(parent, title=_("task_manager_title", name=project["name"]), size=(500, 400), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.project = project
        self._build_ui()
        self._refresh_list()
        self.CentreOnParent()
        
    def _build_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label=_("lbl_tasks"))
        vbox.Add(lbl, 0, wx.ALL, 10)
        
        self.list_tasks = wx.ListBox(self)
        vbox.Add(self.list_tasks, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_add = wx.Button(self, label=_("btn_add_task"))
        self.btn_add.Bind(wx.EVT_BUTTON, self.OnAddTask)
        
        self.btn_toggle = wx.Button(self, label=_("btn_mark_done"))
        self.btn_toggle.Bind(wx.EVT_BUTTON, self.OnToggleDone)
        
        self.btn_delete = wx.Button(self, label=_("btn_delete"))
        self.btn_delete.Bind(wx.EVT_BUTTON, self.OnDeleteTask)
        
        hbox.Add(self.btn_add, 0, wx.RIGHT, 5)
        hbox.Add(self.btn_toggle, 0, wx.RIGHT, 5)
        hbox.Add(self.btn_delete, 0, 0, 0)
        
        vbox.Add(hbox, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        self.SetSizer(vbox)
        
    def _refresh_list(self):
        self.list_tasks.Clear()
        tasks = self.project.get("tasks", [])
        if not tasks:
            self.list_tasks.Append(_("msg_no_tasks"))
            return
            
        for t in tasks:
            status = "[X]" if t.get("is_done") else "[ ]"
            display = f"{status} {t['name']} (Due: {t['deadline_date']})"
            self.list_tasks.Append(display, t)
            
    def OnAddTask(self, event):
        name = core.api.prompt_text(_("task_name_title"), _("task_name_prompt"), "")
        if not name: return
        
        date_str = core.api.prompt_text(_("task_date_title"), _("task_date_prompt"), core.api.get_selected_date() or "")
        if not date_str: return
        
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            core.api.show_message("Error", _("invalid_date"))
            return
            
        new_task = {
            "id": str(uuid.uuid4()),
            "name": name,
            "deadline_date": date_str,
            "is_done": False
        }
        
        if "tasks" not in self.project:
            self.project["tasks"] = []
            
        self.project["tasks"].append(new_task)
        self._save()
        self._refresh_list()
        
    def OnToggleDone(self, event):
        sel = self.list_tasks.GetSelection()
        if sel == wx.NOT_FOUND: return
        
        t = self.list_tasks.GetClientData(sel)
        if not t: return # "No tasks yet" item
        
        was_done = t.get("is_done", False)
        t["is_done"] = not was_done
        
        self._save()
        self._refresh_list()
        self.list_tasks.SetSelection(sel)
        
        # Check overall progress
        if t["is_done"]:
            play_internal_sound("penClick.wav")
            progress = calculate_progress(self.project)
            
            if progress == 100 and not self.project.get("is_completed", False):
                self.project["is_completed"] = True
                self._save()
                speak(_("project_completed", name=self.project["name"]), interrupt=True)
                # Maybe play a triumphant sound here if available, fallback to something else
                play_internal_sound("start.wav") 
            else:
                speak(_("task_completed", name=self.project["name"], percent=progress), interrupt=True)
                
        else:
            self.project["is_completed"] = False
            self._save()
            
    def OnDeleteTask(self, event):
        sel = self.list_tasks.GetSelection()
        if sel == wx.NOT_FOUND: return
        t = self.list_tasks.GetClientData(sel)
        if not t: return
        
        self.project["tasks"].remove(t)
        self._save()
        self._refresh_list()

    def _save(self):
        projects = load_projects()
        for i, p in enumerate(projects):
            if p["id"] == self.project["id"]:
                projects[i] = self.project
                break
        save_projects(projects)


class ProjectManagerDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("project_manager_title"), size=(600, 500), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._build_ui()
        self._refresh_list()
        self.CentreOnParent()
        
    def _build_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label=_("lbl_projects"))
        lbl.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(lbl, 0, wx.ALL, 10)
        
        self.list_projects = wx.ListBox(self)
        vbox.Add(self.list_projects, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_new = wx.Button(self, label=_("btn_new_project"))
        self.btn_new.Bind(wx.EVT_BUTTON, self.OnNewProject)
        
        self.btn_tasks = wx.Button(self, label=_("btn_manage_tasks"))
        self.btn_tasks.Bind(wx.EVT_BUTTON, self.OnManageTasks)
        
        self.btn_delete = wx.Button(self, label=_("btn_delete"))
        self.btn_delete.Bind(wx.EVT_BUTTON, self.OnDeleteProject)
        
        hbox.Add(self.btn_new, 0, wx.RIGHT, 5)
        hbox.Add(self.btn_tasks, 0, wx.RIGHT, 5)
        hbox.Add(self.btn_delete, 0, 0, 0)
        
        vbox.Add(hbox, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        self.SetSizer(vbox)
        
    def _refresh_list(self):
        self.list_projects.Clear()
        projects = load_projects()
        
        if not projects:
            self.list_projects.Append(_("msg_no_projects"))
            return
            
        for p in projects:
            progress = calculate_progress(p)
            status = "[DONE]" if p.get("is_completed") else f"[{progress}%]"
            display = f"{status} {p['name']}"
            if p.get("description"):
                display += f" - {p['description']}"
            self.list_projects.Append(display, p)
            
    def OnNewProject(self, event):
        name = core.api.prompt_text(_("project_name_title"), _("project_name_prompt"), "")
        if not name: return
        
        desc = core.api.prompt_text(_("project_desc_title"), _("project_desc_prompt"), "")
        
        new_project = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": desc or "",
            "is_completed": False,
            "tasks": []
        }
        
        projects = load_projects()
        projects.append(new_project)
        save_projects(projects)
        self._refresh_list()
        
    def OnManageTasks(self, event):
        sel = self.list_projects.GetSelection()
        if sel == wx.NOT_FOUND: return
        p = self.list_projects.GetClientData(sel)
        if not p: return
        
        dlg = TaskManagerDialog(self, p)
        dlg.ShowModal()
        dlg.Destroy()
        
        self._refresh_list()
        self.list_projects.SetSelection(sel)
        
    def OnDeleteProject(self, event):
        sel = self.list_projects.GetSelection()
        if sel == wx.NOT_FOUND: return
        p = self.list_projects.GetClientData(sel)
        if not p: return
        
        msg = _("delete_confirm", name=p["name"])
        if core.api.prompt_yes_no("Confirm Delete", msg):
            projects = load_projects()
            projects = [proj for proj in projects if proj["id"] != p["id"]]
            save_projects(projects)
            self._refresh_list()

def open_project_manager():
    top = wx.GetApp().GetTopWindow()
    if top:
        dlg = ProjectManagerDialog(top)
        dlg.ShowModal()
        dlg.Destroy()

def register(bus):
    core.hotkeys.register_action(
        "Project System", 
        "open_project_manager", 
        "Open Project Manager", 
        ord('P'), 
        True, # Ctrl
        open_project_manager,
        default_shift=True # Shift
    )
    
    bus.subscribe("on_date_changed", on_date_changed)
