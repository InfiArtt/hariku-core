import logging

logger = logging.getLogger(__name__)

# Format: {"Category Name": [ {"name": panel_name, "create": create_func, "apply": apply_func}, ... ] }
_panels = {}

def register_panel(category, panel_name, create_func, apply_func=None):
    """
    Mendaftarkan panel pengaturan ke Unified Preferences.
    - category: Kategori panel (misal: "Extensions").
    - panel_name: Nama panel (misal: "NASA Settings").
    - create_func: Fungsi(parent_window) yang mengembalikan instance wx.Panel.
    - apply_func: Fungsi() yang dipanggil saat user menekan OK di jendela Preferences.
    """
    if category not in _panels:
        _panels[category] = []
    
    _panels[category].append({
        "name": panel_name,
        "create": create_func,
        "apply": apply_func
    })
    logger.info(f"Registered preference panel: [{category}] {panel_name}")

def get_all_panels():
    return _panels
