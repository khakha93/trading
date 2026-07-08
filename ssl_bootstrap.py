import os
import ssl
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def apply_ssl_bootstrap() -> bool:
    """Apply a Windows-safe SSL certificate bootstrap once per interpreter."""
    if sys.platform != "win32":
        return False

    try:
        import certifi
    except Exception:
        return False

    ca_bundle = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)

    if not getattr(ssl.SSLContext, "_trading_ssl_patched", False):
        orig_load_windows_store_certs = getattr(ssl.SSLContext, "_load_windows_store_certs", None)
        if orig_load_windows_store_certs is not None:
            def patched_load_windows_store_certs(self, storename, purpose):
                try:
                    orig_load_windows_store_certs(self, storename, purpose)
                except Exception:
                    try:
                        self.load_verify_locations(ca_bundle)
                    except Exception:
                        pass

            ssl.SSLContext._load_windows_store_certs = patched_load_windows_store_certs
            ssl.SSLContext._trading_ssl_patched = True

    if hasattr(ssl, "create_default_context") and not getattr(ssl, "_trading_create_default_context_patched", False):
        orig_create_default_context = ssl.create_default_context

        def safe_create_default_context(*args, **kwargs):
            try:
                ctx = orig_create_default_context(*args, **kwargs)
            except TypeError:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            try:
                ctx.load_verify_locations(ca_bundle)
            except Exception:
                pass
            return ctx

        ssl.create_default_context = safe_create_default_context
        ssl._trading_create_default_context_patched = True

    return True
