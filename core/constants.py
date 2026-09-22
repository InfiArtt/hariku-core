# hariku2/core/constants.py

APP_NAME = "Hariku"
CORE_VERSION = "2.2.0"

# Memisahkan Mayor dan Minor untuk keperluan validasi ekstensi (misal: "2.0")
_parts = CORE_VERSION.split(".")
if len(_parts) >= 2:
    CORE_VERSION_FLOAT = float(f"{_parts[0]}.{_parts[1]}")
else:
    CORE_VERSION_FLOAT = float(_parts[0])
