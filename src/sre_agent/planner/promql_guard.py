from __future__ import annotations

import re

ALLOWED_FUNCTIONS = frozenset(
    {
        "rate",
        "irate",
        "increase",
        "sum",
        "avg",
        "max",
        "min",
        "count",
        "histogram_quantile",
        "topk",
        "bottomk",
        "quantile",
        "abs",
        "clamp",
        "clamp_min",
        "clamp_max",
        "avg_over_time",
        "max_over_time",
        "min_over_time",
        "last_over_time",
        "count_over_time",
        "stddev_over_time",
        "stdvar_over_time",
        "group",
        "count_values",
        "absent",
        "absent_over_time",
        "label_replace",
        "label_join",
        "round",
        "floor",
        "ceil",
        "sqrt",
        "exp",
        "ln",
        "log2",
        "log10",
        "time",
        "vector",
        "scalar",
        "sort",
        "sort_desc",
        "holt_winters",
        "predict_linear",
        "deriv",
        "delta",
        "idelta",
        "resets",
        "changes",
        "timestamp",
    }
)
KEYWORD_CALLS = frozenset(
    {"by", "without", "on", "group_left", "group_right", "and", "or", "unless", "bool", "ignoring"}
)
FORBIDDEN_SUBSTR = ("eval(", "/api/v1/admin", "delete_series", "snapshot")
FUNC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
RANGE_RE = re.compile(r"\b(rate|irate|increase)\s*\([^)]*\[(\d+)(ms|s|m|h)\]", re.I)
UNBOUNDED_RE = re.compile(r"=~\s*['\"](\.\*|\.\+)['\"]")
UNIT_TO_SECONDS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}


class PromQLViolation(ValueError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def validate_promql(query: str, *, max_length: int = 2000) -> str:
    q = (query or "").strip()
    reasons: list[str] = []
    if not q:
        raise PromQLViolation(["empty query"])
    if len(q) > max_length:
        reasons.append(f"query longer than {max_length}")
    lower = q.lower()
    for bad in FORBIDDEN_SUBSTR:
        if bad in lower:
            reasons.append(f"forbidden fragment: {bad}")
    if UNBOUNDED_RE.search(q):
        reasons.append("unbounded regex selector")
    for name in FUNC_RE.findall(q):
        key = name.lower()
        if key in KEYWORD_CALLS:
            continue
        if key not in ALLOWED_FUNCTIONS:
            reasons.append(f"unknown function: {name}")
    for m in RANGE_RE.finditer(q):
        n = int(m.group(2))
        sec = n * UNIT_TO_SECONDS[m.group(3)]
        if sec < 60 or sec > 3600:
            reasons.append("rate/increase range must be in [1m, 1h]")
    if reasons:
        raise PromQLViolation(reasons)
    return q
