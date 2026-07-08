import importlib
import sys


def test_loads_secrets_when_env_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_KEY", raising=False)
    monkeypatch.delenv("APP_SECRET", raising=False)
    monkeypatch.delenv("CUST_TYPE", raising=False)

    sys.modules.pop("src.config", None)
    config = importlib.import_module("src.config")

    settings = config.load_settings(
        secrets={"APP_KEY": "streamlit-key", "APP_SECRET": "streamlit-secret", "CUST_TYPE": "B"}
    )

    assert settings["APP_KEY"] == "streamlit-key"
    assert settings["APP_SECRET"] == "streamlit-secret"
    assert settings["CUST_TYPE"] == "B"
    assert config.APP_KEY == "streamlit-key"
    assert config.APP_SECRET == "streamlit-secret"
    assert config.CUST_TYPE == "B"
