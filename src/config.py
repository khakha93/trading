import os
from pathlib import Path
from typing import Any
from dotenv import load_dotenv


BASE_URL = "https://openapi.koreainvestment.com:9443"  # 해외옵션 시세조회는 실전투자만 지원
CACHE_FILE = os.path.join("data", ".token_cache.json")
MASTER_FILE = os.path.join("data", "fostkcode.mst")
MASTER_ZIP = os.path.join("data", "fostkcode.mst.zip")
MASTER_URL = "https://new.real.download.dws.co.kr/common/master/fostkcode.mst.zip"


def _load_local_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    env_candidates = [project_root / ".env", project_root / "config.env"]

    for candidate in env_candidates:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break

    load_dotenv(override=False)


def _read_setting(name: str, default: str = None, secrets: Any = None) -> str:
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return value

    if secrets is not None:
        if hasattr(secrets, "get"):
            value = secrets.get(name)
        elif isinstance(secrets, dict):
            value = secrets.get(name)
        else:
            value = None

        if value is not None and str(value).strip():
            return str(value)

    return default


def load_settings(secrets: Any = None) -> dict:
    _load_local_env()

    settings = {
        "APP_KEY": _read_setting("APP_KEY", None, secrets),
        "APP_SECRET": _read_setting("APP_SECRET", None, secrets),
        "CUST_TYPE": _read_setting("CUST_TYPE", "P", secrets),
    }

    globals()["APP_KEY"] = settings["APP_KEY"]
    globals()["APP_SECRET"] = settings["APP_SECRET"]
    globals()["CUST_TYPE"] = settings["CUST_TYPE"]

    return settings


load_settings()

APP_KEY = None
APP_SECRET = None
CUST_TYPE = "P"

load_settings()
