from sre_agent.channels.dingtalk import dingtalk_routes_enabled
from sre_agent.config import Settings


def test_dingtalk_disabled_without_secret(monkeypatch):
    monkeypatch.setenv("SRE_AGENT_LLM_BASE_URL", "http://x")
    monkeypatch.setenv("SRE_AGENT_LLM_API_KEY", "k")
    monkeypatch.delenv("SRE_AGENT_DINGTALK_APP_SECRET", raising=False)
    s = Settings(_env_file=None)
    assert dingtalk_routes_enabled(s) is False
