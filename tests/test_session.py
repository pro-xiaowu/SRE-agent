from sre_agent.session import build_session_store


def test_memory_roundtrip():
    s = build_session_store(None)
    s.append("a", "human", "hi")
    s.append("a", "ai", "hello")
    assert s.history("a") == [("human", "hi"), ("ai", "hello")]
    assert s.history("b") == []


def test_clarification_counter():
    s = build_session_store(None)
    assert s.clarification_count("x") == 0
    assert s.incr_clarification("x") == 1
    assert s.incr_clarification("x") == 2
    s.reset_clarification("x")
    assert s.clarification_count("x") == 0


def test_session_catalog_roundtrip():
    s = build_session_store(None)
    s.create_session("a", "告警巡检")
    s.append("a", "human", "现在有哪些告警？")

    sessions = s.list_sessions()
    assert sessions[0]["id"] == "a"
    assert sessions[0]["title"] == "告警巡检"
    assert sessions[0]["message_count"] == 1

    s.delete_session("a")
    assert s.list_sessions() == []
    assert s.history("a") == []
