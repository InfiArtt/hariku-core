# hariku2/ui/input_gestures_dialog.py
import wx
import ctypes
import ctypes.wintypes as _wt
import core.hotkeys

class InputGesturesPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        # Ambil salinan lokal
        self.pending_config = core.hotkeys.get_resolved_config()
        
        self.InitUI()
        self.LoadActions()
        
    def InitUI(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label="Input Gestures (Extensions & Core Shortcuts)")
        vbox.Add(lbl, 0, wx.ALL, 10)
        
        self.tree = wx.TreeCtrl(self, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT)
        vbox.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        self.chk_global = wx.CheckBox(self, label="Make this shortcut Global (Works everywhere in Windows)")
        self.chk_global.Disable()
        vbox.Add(self.chk_global, 0, wx.ALL | wx.ALIGN_LEFT, 10)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_add = wx.Button(self, label="Add Key")
        self.btn_remove = wx.Button(self, label="Remove Key")
        
        self.btn_add.Disable()
        self.btn_remove.Disable()
        
        hbox.Add(self.btn_add, 0, wx.RIGHT, 10)
        hbox.Add(self.btn_remove, 0, wx.RIGHT, 10)
        
        hbox.AddStretchSpacer()
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(vbox)
        
        self.Bind(wx.EVT_BUTTON, self.OnAddShortcut, self.btn_add)
        self.Bind(wx.EVT_BUTTON, self.OnRemoveShortcut, self.btn_remove)
        
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnTreeSelection, self.tree)
        self.Bind(wx.EVT_CHECKBOX, self.OnGlobalToggle, self.chk_global)
        
    def LoadActions(self):
        self.tree.DeleteAllItems()
        self.root = self.tree.AddRoot("Root")
        
        categories = {}
        for action_id, action in core.hotkeys.actions.items():
            cat = action.extension_name
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((action_id, action))
            
        for cat in sorted(categories.keys()):
            cat_node = self.tree.AppendItem(self.root, cat)
            self.tree.SetItemData(cat_node, {"type": "category", "name": cat})
            
            for action_id, action in categories[cat]:
                action_node = self.tree.AppendItem(cat_node, action.description)
                self.tree.SetItemData(action_node, {"type": "action", "action_id": action_id})
                
                bindings = self.pending_config.get(action_id, [])
                for b in bindings:
                    kc, ctrl, shift, alt, win, is_global = b["keycode"], b.get("ctrl", False), b.get("shift", False), b.get("alt", False), b.get("win", False), b.get("global", False)
                    self._AppendShortcutNode(action_node, action_id, kc, ctrl, shift, alt, win, is_global)
                    
    def _AppendShortcutNode(self, parent_node, action_id, kc, ctrl, shift, alt, win, is_global):
        shortcut_str = core.hotkeys.format_key_name(kc, ctrl, shift, alt, win)
        scope_str = "GLOBAL" if is_global else "LOCAL"
        node_text = f"{shortcut_str} [{scope_str}]"
        
        shortcut_node = self.tree.AppendItem(parent_node, node_text)
        self.tree.SetItemData(shortcut_node, {
            "type": "shortcut",
            "action_id": action_id,
            "keycode": kc,
            "ctrl": ctrl,
            "shift": shift,
            "alt": alt,
            "win": win,
            "is_global": is_global
        })
        return shortcut_node
                    
    def OnTreeSelection(self, event):
        item = event.GetItem()
        data = self.tree.GetItemData(item)
        
        self.btn_add.Disable()
        self.btn_remove.Disable()
        self.chk_global.Disable()
        self.chk_global.SetValue(False)
        
        if not data: return
        
        if data["type"] == "action":
            self.btn_add.Enable()
        elif data["type"] == "shortcut":
            self.btn_remove.Enable()
            # Only allow Global toggle if the shortcut uses at least one modifier key.
            # Single-key hotkeys (e.g. just "F") should never be global.
            has_modifier = data.get("ctrl", False) or data.get("shift", False) or data.get("alt", False) or data.get("win", False)
            if has_modifier:
                self.chk_global.Enable()
                self.chk_global.SetValue(data["is_global"])
            else:
                self.chk_global.Disable()
                self.chk_global.SetValue(False)
            
    def OnGlobalToggle(self, event):
        item = self.tree.GetSelection()
        data = self.tree.GetItemData(item)
        if data and data["type"] == "shortcut":
            action_id = data["action_id"]
            kc = data["keycode"]
            ctrl = data.get("ctrl", False)
            shift = data.get("shift", False)
            alt = data.get("alt", False)
            win = data.get("win", False)
            has_modifier = ctrl or shift or alt or win
            new_global = self.chk_global.GetValue()
            
            # Safety net: never allow global for keys without a modifier
            if new_global and not has_modifier:
                self.chk_global.SetValue(False)
                return
            
            # Update pending config
            for b in self.pending_config[action_id]:
                if b["keycode"] == kc and b.get("ctrl", False) == ctrl and b.get("shift", False) == shift and b.get("alt", False) == alt and b.get("win", False) == win:
                    b["global"] = new_global
                    
            # Update node UI smoothly
            data["is_global"] = new_global
            self.tree.SetItemData(item, data)
            
            shortcut_str = core.hotkeys.format_key_name(kc, ctrl, shift, alt, win)
            scope_str = "GLOBAL" if new_global else "LOCAL"
            self.tree.SetItemText(item, f"{shortcut_str} [{scope_str}]")
            
    def _RemoveDuplicateKey(self, keycode, ctrl, shift, alt, win):
        for aid, bindings in self.pending_config.items():
            self.pending_config[aid] = [b for b in bindings if not (b["keycode"] == keycode and b.get("ctrl", False) == ctrl and b.get("shift", False) == shift and b.get("alt", False) == alt and b.get("win", False) == win)]
            
    def OnAddShortcut(self, event):
        item = self.tree.GetSelection()
        data = self.tree.GetItemData(item)
        if not data or data["type"] != "action": return
        
        action_id = data["action_id"]
        action = core.hotkeys.actions[action_id]
        
        dlg = CaptureKeyDialog(self, f"Press new shortcut key for:\n{action.description}")
        if dlg.ShowModal() == wx.ID_OK:
            keycode, ctrl, shift, alt, win = dlg.GetCapturedKey()
            
            self._RemoveDuplicateKey(keycode, ctrl, shift, alt, win)
            
            if action_id not in self.pending_config:
                self.pending_config[action_id] = []
                
            exists = any(b["keycode"] == keycode and b.get("ctrl", False) == ctrl and b.get("shift", False) == shift and b.get("alt", False) == alt and b.get("win", False) == win for b in self.pending_config[action_id])
            if not exists:
                self.pending_config[action_id].append({"keycode": keycode, "ctrl": ctrl, "shift": shift, "alt": alt, "win": win, "global": False})
                self._AppendShortcutNode(item, action_id, keycode, ctrl, shift, alt, win, False)
                self.tree.Expand(item)
                
            self._CleanOrphanedNodes()
            
        dlg.Destroy()
        
    def _CleanOrphanedNodes(self):
        cat_node, cookie = self.tree.GetFirstChild(self.root)
        while cat_node.IsOk():
            act_node, cookie2 = self.tree.GetFirstChild(cat_node)
            while act_node.IsOk():
                action_data = self.tree.GetItemData(act_node)
                action_id = action_data["action_id"]
                
                short_node, cookie3 = self.tree.GetFirstChild(act_node)
                to_delete = []
                while short_node.IsOk():
                    data = self.tree.GetItemData(short_node)
                    kc = data["keycode"]
                    ctrl = data.get("ctrl", False)
                    shift = data.get("shift", False)
                    alt = data.get("alt", False)
                    win = data.get("win", False)
                    
                    exists = any(b["keycode"] == kc and b.get("ctrl", False) == ctrl and b.get("shift", False) == shift and b.get("alt", False) == alt and b.get("win", False) == win for b in self.pending_config[action_id])
                    if not exists:
                        to_delete.append(short_node)
                        
                    short_node, cookie3 = self.tree.GetNextChild(act_node, cookie3)
                    
                for n in to_delete:
                    self.tree.Delete(n)
                    
                act_node, cookie2 = self.tree.GetNextChild(cat_node, cookie2)
            cat_node, cookie = self.tree.GetNextChild(self.root, cookie)
        
    def OnRemoveShortcut(self, event):
        item = self.tree.GetSelection()
        data = self.tree.GetItemData(item)
        if not data or data["type"] != "shortcut": return
        
        action_id = data["action_id"]
        kc = data["keycode"]
        ctrl = data.get("ctrl", False)
        shift = data.get("shift", False)
        alt = data.get("alt", False)
        win = data.get("win", False)
        
        if action_id in self.pending_config:
            self.pending_config[action_id] = [b for b in self.pending_config[action_id] if not (b["keycode"] == kc and b.get("ctrl", False) == ctrl and b.get("shift", False) == shift and b.get("alt", False) == alt and b.get("win", False) == win)]
            
        self.tree.Delete(item)

    def ApplyChanges(self):
        core.hotkeys.apply_new_config(self.pending_config)


# ---------------------------------------------------------------------------
# Module-level keyboard hook state (must be global to survive GC)
# ---------------------------------------------------------------------------

_WH_KEYBOARD_LL = 13
_WM_KEYDOWN     = 0x0100
_WM_KEYUP       = 0x0101
_WM_SYSKEYDOWN  = 0x0104
_WM_SYSKEYUP    = 0x0105

class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode',      _wt.DWORD),
        ('scanCode',    _wt.DWORD),
        ('flags',       _wt.DWORD),
        ('time',        _wt.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]

_HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_int, _wt.WPARAM, _wt.LPARAM)
_user32   = ctypes.windll.user32

# Explicit signatures — prevents "expected WinFunctionType" errors
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, _wt.HINSTANCE, _wt.DWORD]
_user32.SetWindowsHookExW.restype  = ctypes.c_void_p
_user32.CallNextHookEx.argtypes    = [ctypes.c_void_p, ctypes.c_int, _wt.WPARAM, _wt.LPARAM]
_user32.CallNextHookEx.restype     = ctypes.c_long
_user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
_user32.UnhookWindowsHookEx.restype  = _wt.BOOL

_pressed_keys: set = set()   # VK codes currently held
_hook_handle        = None
_hook_cb            = None   # keep HOOKPROC alive

# All VK codes that should be treated as modifiers (generic + left/right variants)
_ALL_MODIFIER_VKS = {
    0x10, 0x11, 0x12,        # generic Shift, Ctrl, Alt
    0x5B, 0x5C,              # LWin, RWin
    0xA0, 0xA1,              # LShift, RShift
    0xA2, 0xA3,              # LCtrl, RCtrl
    0xA4, 0xA5,              # LAlt, RAlt
}

def _raw_hook(nCode, wParam, lParam):
    if nCode >= 0:
        vk = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents.vkCode
        if wParam in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            _pressed_keys.add(vk)
        elif wParam in (_WM_KEYUP, _WM_SYSKEYUP):
            _pressed_keys.discard(vk)
        # Suppress any non-modifier, non-Escape key so the capture dialog can
        # see it. This includes single-letter keys pressed without a modifier.
        if vk not in _ALL_MODIFIER_VKS and vk != 0x1B:  # 0x1B = Escape
            return 1  # suppress so the key doesn't leak to Hariku or other apps
    return _user32.CallNextHookEx(None, nCode, wParam, lParam)

def _install_ll_hook():
    global _hook_handle, _hook_cb
    _hook_cb     = _HOOKPROC(_raw_hook)
    _hook_handle = _user32.SetWindowsHookExW(_WH_KEYBOARD_LL, _hook_cb, None, 0)

def _uninstall_ll_hook():
    global _hook_handle
    if _hook_handle:
        _user32.UnhookWindowsHookEx(_hook_handle)
        _hook_handle = None
    _pressed_keys.clear()


# ---------------------------------------------------------------------------
class CaptureKeyDialog(wx.Dialog):
    """
    Opens a small dialog that captures key combos via a WH_KEYBOARD_LL hook.
    The hook runs at system level so Win+key works. A wx.Timer polls the
    shared _pressed_keys set — no wx.CallAfter inside the hook callback.

    Fix: _VK_MODIFIERS includes both generic AND left/right-specific VK codes
    so pressing LCtrl (0xA2) alone is never mistaken for a trigger key.
    Global hotkeys are suspended while the dialog is open so combos like
    Ctrl+N aren't fired by Hariku before being captured.
    """

    # Must match _ALL_MODIFIER_VKS above — used for non_mod filtering in _on_tick
    _VK_MODIFIERS = {
        0x10, 0x11, 0x12,        # generic Shift, Ctrl, Alt
        0x5B, 0x5C,              # LWin, RWin
        0xA0, 0xA1,              # LShift, RShift
        0xA2, 0xA3,              # LCtrl, RCtrl
        0xA4, 0xA5,              # LAlt, RAlt
    }

    _VK_TO_WX = {
        0xBF: ord('/'),  0xBA: ord(';'),  0xBB: ord('='),
        0xBC: ord(','),  0xBD: ord('-'),  0xBE: ord('.'),
        0xC0: ord('`'),  0xDB: ord('['),  0xDC: ord('\\'),
        0xDD: ord(']'),  0xDE: ord("'"),
        0x20: wx.WXK_SPACE,   0x08: wx.WXK_BACK,
        0x09: wx.WXK_TAB,     0x0D: wx.WXK_RETURN,
        0x1B: wx.WXK_ESCAPE,  0x2E: wx.WXK_DELETE,
        0x25: wx.WXK_LEFT,    0x26: wx.WXK_UP,
        0x27: wx.WXK_RIGHT,   0x28: wx.WXK_DOWN,
        0x21: wx.WXK_PAGEUP,  0x22: wx.WXK_PAGEDOWN,
        0x23: wx.WXK_END,     0x24: wx.WXK_HOME,
        0x70: wx.WXK_F1,  0x71: wx.WXK_F2,  0x72: wx.WXK_F3,  0x73: wx.WXK_F4,
        0x74: wx.WXK_F5,  0x75: wx.WXK_F6,  0x76: wx.WXK_F7,  0x77: wx.WXK_F8,
        0x78: wx.WXK_F9,  0x79: wx.WXK_F10, 0x7A: wx.WXK_F11, 0x7B: wx.WXK_F12,
    }

    _SINGLE_KEY_DELAY_MS = 300  # wait this long before accepting a keypress without modifiers

    def __init__(self, parent, message):
        super().__init__(parent, title="Add Key", size=(380, 180))

        self.keycode = None
        self.ctrl = self.shift = self.alt = self.win = False
        self._committed = False
        self._pending_single_vk = None      # VK held without modifier
        self._pending_single_tick = 0       # tick count while held

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label=message + "\n\nPress a key combination..."),
                 1, wx.ALL | wx.ALIGN_CENTER, 20)

        self._preview = wx.StaticText(self, label="")
        self._preview.SetForegroundColour(wx.Colour(30, 120, 220))
        vbox.Add(self._preview, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        self.SetSizer(vbox)
        self.CentreOnParent()

        _install_ll_hook()
        core.hotkeys.suspend_global_hotkeys()  # pause so registered hotkeys don't fire first

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_tick, self._timer)
        self._timer.Start(30)

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

    def _on_tick(self, _event):
        if self._committed:
            return

        pressed = set(_pressed_keys)   # snapshot

        # Escape cancels the dialog cleanly
        if 0x1B in pressed:
            self._committed = True
            self._timer.Stop()
            _uninstall_ll_hook()
            core.hotkeys.resume_global_hotkeys()
            self.EndModal(wx.ID_CANCEL)
            return

        ctrl  = bool(pressed & {0x11, 0xA2, 0xA3})
        shift = bool(pressed & {0x10, 0xA0, 0xA1})
        alt   = bool(pressed & {0x12, 0xA4, 0xA5})
        win   = bool(pressed & {0x5B, 0x5C})
        any_mod = ctrl or shift or alt or win

        # non_mod = keys that are NOT in our full modifier set
        non_mod = [vk for vk in pressed if vk not in self._VK_MODIFIERS]

        parts = []
        if ctrl:  parts.append("Ctrl")
        if shift: parts.append("Shift")
        if alt:   parts.append("Alt")
        if win:   parts.append("Win")

        if non_mod and any_mod:
            # Modifier + key combo — commit immediately
            vk = non_mod[0]
            parts.append(self._vk_name(vk))
            self._preview.SetLabel(" + ".join(parts))
            self._pending_single_vk = None
            self._commit(vk, ctrl, shift, alt, win)
        elif non_mod and not any_mod:
            # Single key without modifier — record it and start counting
            vk = non_mod[0]
            if self._pending_single_vk != vk:
                # New key pressed — start fresh
                self._pending_single_vk = vk
                self._pending_single_tick = 0
            self._pending_single_tick += 1
            ticks_needed = self._SINGLE_KEY_DELAY_MS // 30
            self._preview.SetLabel(self._vk_name(vk))
            if self._pending_single_tick >= ticks_needed:
                self._commit(vk, False, False, False, False)
        elif parts:
            # Only modifiers held — if user adds a modifier, cancel pending single key
            self._pending_single_vk = None
            self._pending_single_tick = 0
            self._preview.SetLabel(" + ".join(parts) + " + ?")
        else:
            # Nothing pressed — but keep counting if a single key was tapped
            if self._pending_single_vk is not None:
                self._pending_single_tick += 1
                ticks_needed = self._SINGLE_KEY_DELAY_MS // 30
                if self._pending_single_tick >= ticks_needed:
                    self._commit(self._pending_single_vk, False, False, False, False)
            else:
                self._preview.SetLabel("")

    def _commit(self, vk, ctrl, shift, alt, win):
        self._committed = True
        self._timer.Stop()
        _uninstall_ll_hook()
        core.hotkeys.resume_global_hotkeys()

        self.keycode = self._VK_TO_WX.get(vk) if vk in self._VK_TO_WX else (
            vk if (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A) else vk
        )
        self.ctrl  = ctrl
        self.shift = shift
        self.alt   = alt
        self.win   = win
        self.EndModal(wx.ID_OK)

    def _vk_name(self, vk):
        if vk in self._VK_TO_WX:
            wk = self._VK_TO_WX[vk]
            names = {
                wx.WXK_SPACE:"Space", wx.WXK_BACK:"Backspace", wx.WXK_TAB:"Tab",
                wx.WXK_RETURN:"Enter", wx.WXK_ESCAPE:"Escape", wx.WXK_DELETE:"Delete",
                wx.WXK_LEFT:"Left", wx.WXK_RIGHT:"Right", wx.WXK_UP:"Up",
                wx.WXK_DOWN:"Down", wx.WXK_PAGEUP:"PgUp", wx.WXK_PAGEDOWN:"PgDn",
                wx.WXK_HOME:"Home", wx.WXK_END:"End",
            }
            if wk in names: return names[wk]
            if 32 <= wk <= 126: return chr(wk)
        if 0x70 <= vk <= 0x7B: return f"F{vk - 0x6F}"
        if 0x30 <= vk <= 0x39: return chr(vk)
        if 0x41 <= vk <= 0x5A: return chr(vk)
        return f"Key(0x{vk:02X})"

    def _on_close(self, event):
        self._timer.Stop()
        _uninstall_ll_hook()
        core.hotkeys.resume_global_hotkeys()
        event.Skip()

    def _on_destroy(self, event):
        # Safety net: guarantee hook and hotkeys are always restored
        _uninstall_ll_hook()
        core.hotkeys.resume_global_hotkeys()
        event.Skip()

    def GetCapturedKey(self):
        return self.keycode, self.ctrl, self.shift, self.alt, self.win
