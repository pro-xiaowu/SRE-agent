from sre_agent.security.policy import check_text


def test_allow_inspection():
    d = check_text("现在有哪些 firing 告警？")
    assert d.allow is True
    assert d.reason == "ok"
    assert d.write_action is None


def test_reject_empty():
    d = check_text("  \n")
    assert d.allow is False
    assert d.reason == "empty"


def test_reject_silence():
    d = check_text("把 node-disk 告警静默 1 小时")
    assert d.allow is False
    assert d.reason == "write_operation"
    assert d.write_action == "silence"


def test_reject_restart():
    d = check_text("重启 checkout 服务")
    assert d.allow is False
    assert d.reason == "write_operation"
    assert d.write_action == "restart"
