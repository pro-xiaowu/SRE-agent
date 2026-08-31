from sre_agent.security.approvals import build_approval_store


def test_approve_does_not_execute():
    store = build_approval_store(None)
    rec = store.create("silence", '{"alert":"node-disk","duration":"1h"}', "user asked", "u1")
    assert rec.state == "pending"
    done = store.decide(rec.id, True)
    assert done.state == "approved_not_executed"
    assert store.get(rec.id).state == "approved_not_executed"


def test_reject():
    store = build_approval_store(None)
    rec = store.create("restart", "{}", "no", "u1")
    done = store.decide(rec.id, False)
    assert done.state == "rejected"
