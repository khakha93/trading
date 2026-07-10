import os
import subprocess
import sys

from ssl_bootstrap import apply_ssl_bootstrap

apply_ssl_bootstrap()


def main() -> int:
    if os.environ.get("STREAMLIT_SERVER_PORT") or os.environ.get("STREAMLIT_GLOBAL"):
        import app  # noqa: F401
        return 0

    project_root = os.path.dirname(os.path.abspath(__file__))
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [project_root, os.environ.get("PYTHONPATH", "")]))

    cmd = [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", "8502"]
    env = os.environ.copy()
    env.setdefault("SSL_CERT_FILE", os.environ.get("SSL_CERT_FILE", ""))
    env.setdefault("REQUESTS_CA_BUNDLE", os.environ.get("REQUESTS_CA_BUNDLE", ""))
    return subprocess.call(cmd, cwd=project_root, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
