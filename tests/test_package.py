import sys

from sre_agent import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_python_constraint_documented():
    assert sys.version_info >= (3, 11)
    assert sys.version_info < (3, 14)
