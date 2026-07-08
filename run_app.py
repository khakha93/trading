# --- Windows SSL Bug Patch ---
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

import streamlit.web.cli as stcli

if __name__ == '__main__':
    sys.argv = ["streamlit", "run", "app.py"]
    sys.exit(stcli.main())
