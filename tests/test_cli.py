from sre_agent.cli import main


def test_ask_help():
    code = main(["--help"])
    assert code == 0


def test_ask_requires_text():
    code = main(["ask"])
    assert code != 0
