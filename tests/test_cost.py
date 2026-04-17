import pytest

from kindle_news.cost import CostTracker


def test_budget_guardrail_raises() -> None:
    tracker = CostTracker(max_cost_usd=1.0, input_cost_per_1m=1.0, output_cost_per_1m=1.0)
    tracker.add_usage(900_000, 200_000)
    with pytest.raises(RuntimeError):
        tracker.ensure_under_budget()
