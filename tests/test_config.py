from backend.config import load_settings


def test_anthropic_api_key_loads_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = load_settings()
    assert s.anthropic_api_key == "sk-ant-test"


def test_anthropic_api_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = load_settings()
    assert s.anthropic_api_key == ""
