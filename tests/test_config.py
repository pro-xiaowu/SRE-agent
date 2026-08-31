from sre_agent.config import Settings, load_settings


def test_allow_ad_hoc_defaults_false(monkeypatch):
    monkeypatch.setenv("SRE_AGENT_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("SRE_AGENT_LLM_API_KEY", "sk-test")
    s = load_settings()
    assert s.allow_ad_hoc_promql is False
    assert s.llm_model == "qwen-plus"
    assert s.query_timeout_seconds == 15
    assert s.max_points == 1000
    assert s.read_only is True
    assert s.prom_url == "http://localhost:9090"
    assert s.am_url == "http://localhost:9093"
    assert s.database_url == "postgresql://sre_agent:sre_agent@localhost:5432/sre_agent"


def test_missing_llm_url_raises(monkeypatch):
    monkeypatch.delenv("SRE_AGENT_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SRE_AGENT_LLM_API_KEY", raising=False)
    try:
        Settings(_env_file=None)
    except Exception as exc:
        text = str(exc).lower()
        assert "llm_base_url" in text or "llm_api_key" in text
    else:
        raise AssertionError("expected validation error")
