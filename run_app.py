# --- Windows SSL Bug Patch ---
import os
import subprocess
import sys
import ssl

if sys.platform == 'win32':
    try:
        orig_load_windows_store_certs = ssl.SSLContext._load_windows_store_certs
        def patched_load_windows_store_certs(self, storename, purpose):
            try:
                orig_load_windows_store_certs(self, storename, purpose)
            except Exception:
                try:
                    import certifi
                    self.load_verify_locations(certifi.where())
                except Exception:
                    pass
        ssl.SSLContext._load_windows_store_certs = patched_load_windows_store_certs
    except Exception:
        pass
# -----------------------------


def main() -> int:
    if os.environ.get("STREAMLIT_SERVER_PORT") or os.environ.get("STREAMLIT_GLOBAL"):
        import app  # noqa: F401
        return 0

    cmd = [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true"]
    return subprocess.call(cmd)


if __name__ == '__main__':
    raise SystemExit(main())
