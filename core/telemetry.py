import threading
import urllib.request
import json
import logging
import platform
import uuid
import sys

import core.api
import core.constants
import core.extension_manager

logger = logging.getLogger(__name__)

# Telemetry is DISABLED: the old novarealm.cloud endpoint was retired and there
# is no POST-capable replacement (static GitHub hosting can't accept POST).
# The functions are kept as no-ops so callers (core startup) stay unchanged.
TELEMETRY_DISABLED = True

API_URL = None  # retired

def _generate_session_id():
    """Menghasilkan anonymous ID unik per pengguna (hanya sekali)"""
    config = core.api.load_data("Core")
    if "telemetry_id" not in config:
        # UUID4 benar-benar acak, tidak mengandung informasi hardware atau MAC address.
        config["telemetry_id"] = str(uuid.uuid4())
        core.api.save_data("Core", config)
    return config["telemetry_id"]

def is_enabled():
    config = core.api.load_data("Core")
    # Default ON (Opt-Out model), kecuali user mematikan di setting/onboarding
    return config.get("telemetry_enabled", True)

def _send_ping():
    if TELEMETRY_DISABLED:
        return
    if not is_enabled():
        return

    try:
        config = core.api.load_data("Core")
        lang = config.get("language", "en")
        
        # Ambil list ekstensi yang aktif
        ext_list = list(core.extension_manager.LOADED_EXTENSIONS.keys())
        
        payload = {
            "session_id": _generate_session_id(),
            "app_version": core.constants.CORE_VERSION,
            "os_info": platform.platform(),
            "language": lang,
            "active_extensions": ext_list
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(API_URL, data=data, headers={'Content-Type': 'application/json'})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.getcode() == 201:
                logger.info("Telemetry ping sent successfully.")
    except Exception as e:
        # Gagal kirim telemetri tidak boleh mengganggu UX pengguna
        logger.debug(f"Telemetry ping failed silently: {e}")

def record_startup():
    """Dipanggil saat aplikasi baru nyala. No-op while telemetry is disabled."""
    if TELEMETRY_DISABLED:
        return
    threading.Thread(target=_send_ping, daemon=True).start()
