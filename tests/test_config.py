from backend.config import load_settings


def test_deepseek_api_key_loads_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    s = load_settings()
    assert s.deepseek_api_key == "sk-deepseek-test"


def test_deepseek_api_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    s = load_settings()
    assert s.deepseek_api_key == ""
