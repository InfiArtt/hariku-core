"""
hariku2/core/webview.py

Core API untuk menampilkan HTML content di jendela WebView yang terisolasi
dari proses utama Hariku (sehingga tidak crash karena keyboard hook).

Usage dari extension:
    import core.webview
    core.webview.show_html(html_string, title="Judul Jendela")

    # Atau jika HTML sudah ada di file:
    core.webview.show_html_file(filepath, title="Judul Jendela")
"""

import os
import sys
import tempfile
import subprocess
import uuid
import logging

logger = logging.getLogger(__name__)

# Path ke script host
_HOST_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webview_host.py")


def _get_python_exe():
    """Dapatkan path Python executable yang sedang berjalan."""
    return sys.executable


def show_html(html_content: str, title: str = "Hariku Viewer",
              width: int = 850, height: int = 650) -> bool:
    """
    Tampilkan string HTML di jendela WebView yang terisolasi.

    Karena berjalan di subprocess terpisah, jendela ini:
    - Tidak bisa crash proses Hariku
    - Tidak terpengaruh WH_KEYBOARD_LL hook
    - Mendukung NVDA Browse Mode penuh (H, T, L, K, I)

    Args:
        html_content: String HTML lengkap (termasuk <html> dan <head>).
        title: Judul jendela yang ditampilkan.
        width: Lebar jendela awal (pixels).
        height: Tinggi jendela awal (pixels).

    Returns:
        True jika subprocess berhasil diluncurkan.
    """
    try:
        # [SEC MED-1] Use UUID-based filename to prevent predictable temp file
        # race conditions and content injection by other local processes.
        temp_dir = os.path.join(tempfile.gettempdir(), "hariku2", "webview")
        os.makedirs(temp_dir, exist_ok=True)

        unique_id = uuid.uuid4().hex
        html_path = os.path.join(temp_dir, f"view_{unique_id}.html")

        # Exclusive creation (O_EXCL) prevents TOCTOU: if file somehow
        # already exists with same UUID, we fail-safe rather than overwrite.
        fd = os.open(html_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)

        return show_html_file(html_path, title, width, height)

    except Exception as e:
        logger.error("core.webview.show_html failed: %s", e)
        return False


def show_html_file(html_path: str, title: str = "Hariku Viewer",
                   width: int = 850, height: int = 650) -> bool:
    """
    Tampilkan file HTML di jendela WebView yang terisolasi.

    Args:
        html_path: Path absolut ke file HTML.
        title: Judul jendela.
        width: Lebar jendela awal.
        height: Tinggi jendela awal.

    Returns:
        True jika subprocess berhasil diluncurkan.
    """
    try:
        python_exe = _get_python_exe()

        # CREATE_NO_WINDOW agar tidak muncul konsol hitam
        flags = 0x08000000  # CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [
                python_exe,
                _HOST_SCRIPT,
                html_path,
                title,
                str(width),
                str(height),
            ],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        logger.info("WebView subprocess launched (PID %s) for: %s", proc.pid, html_path)
        return True

    except Exception as e:
        logger.error("core.webview.show_html_file failed: %s", e)
        return False
