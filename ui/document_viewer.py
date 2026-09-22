# hariku2/ui/document_viewer.py
import wx
import os

class DocumentViewerDialog(wx.Dialog):
    def __init__(self, parent, title, filename):
        # Gunakan style wx.RESIZE_BORDER agar dialog bisa diubah ukurannya
        super().__init__(parent, title=title, size=(600, 450), 
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.filename = filename
        self._init_ui()
        self.CentreOnParent()
        
    def _init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Read-only multiline text control
        self.text_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        
        # Set font agar nyaman dibaca (opsional, tapi bagus untuk low vision)
        font = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.text_ctrl.SetFont(font)
        
        self._load_content()
        
        vbox.Add(self.text_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        
        # Tombol Close
        btn_close = wx.Button(self, wx.ID_CANCEL, label="Close")
        vbox.Add(btn_close, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 10)
        
        from core.i18n import apply_rtl_layout
        apply_rtl_layout(self)
        
        self.SetSizer(vbox)
        
    def _load_content(self):
        import core.i18n
        import sys
        
        lang = core.i18n.get_current_language()
        
        # Tentukan base dir (karena jika di-compile Nuitka, letaknya bisa berbeda)
        import builtins as _builtins
        if getattr(sys, 'frozen', False) or hasattr(_builtins, '__compiled__') or hasattr(sys, 'nuitka_version'):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            
        docs_dir = os.path.join(base_dir, "docs")
        
        # Coba buka dari folder bahasa yang sedang aktif
        target_file = os.path.join(docs_dir, lang, self.filename)
        
        # Jika tidak ada, fallback ke bahasa Inggris (en)
        if not os.path.exists(target_file):
            target_file = os.path.join(docs_dir, "en", self.filename)
            
        if os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    content = f.read()
                self.text_ctrl.SetValue(content)
            except Exception as e:
                self.text_ctrl.SetValue(f"Error loading document: {e}")
        else:
            self.text_ctrl.SetValue(f"Document not found: {self.filename}\n\nMake sure the file exists in the docs folder.")

def show_document(parent, title, filename):
    dlg = DocumentViewerDialog(parent, title, filename)
    dlg.ShowModal()
    dlg.Destroy()
