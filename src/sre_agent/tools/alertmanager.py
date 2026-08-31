from langchain_core.tools import tool

from sre_agent.tools import registry


@tool
def am_list_alerts(filter: str = "") -> str:
    """List Alertmanager alerts (read-only)."""
    return registry.call_am_list_alerts(filter)


@tool
def am_list_silences() -> str:
    """List Alertmanager silences (read-only)."""
    return registry.call_am_list_silences()
