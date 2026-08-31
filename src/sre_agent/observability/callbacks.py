from __future__ import annotations

import time

from langchain_core.callbacks import BaseCallbackHandler

from sre_agent.observability.metrics import LLM_LATENCY, LLM_TOKENS, PROM_DURATION, PROM_QUERIES


class MetricsHandler(BaseCallbackHandler):
    def __init__(self, step: str = "classify") -> None:
        super().__init__()
        self.step = step
        self._llm_start: float | None = None

    def on_llm_start(self, serialized, prompts, **kwargs) -> None:  # noqa: ANN001
        self._llm_start = time.perf_counter()

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: ANN001
        model = "unknown"
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            model = str(llm_output.get("model_name") or llm_output.get("model") or "unknown")
            usage = llm_output.get("token_usage") or {}
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            if prompt:
                LLM_TOKENS.labels(model=model, direction="in").inc(prompt)
            if completion:
                LLM_TOKENS.labels(model=model, direction="out").inc(completion)
        if self._llm_start is not None:
            LLM_LATENCY.labels(model=model, step=self.step).observe(time.perf_counter() - self._llm_start)
            self._llm_start = None

    def on_tool_end(self, output, **kwargs) -> None:  # noqa: ANN001
        PROM_QUERIES.labels(api="tool", status="ok").inc()

    def on_chain_error(self, error, **kwargs) -> None:  # noqa: ANN001
        PROM_DURATION.labels(api="chain").observe(0)
