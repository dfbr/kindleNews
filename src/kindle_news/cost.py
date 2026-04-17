from __future__ import annotations


class CostTracker:
    def __init__(
        self,
        max_cost_usd: float,
        input_cost_per_1m: float,
        output_cost_per_1m: float,
    ) -> None:
        self.max_cost_usd = max_cost_usd
        self.input_cost_per_1m = input_cost_per_1m
        self.output_cost_per_1m = output_cost_per_1m
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def total_cost_usd(self) -> float:
        return (self.input_tokens / 1_000_000) * self.input_cost_per_1m + (
            self.output_tokens / 1_000_000
        ) * self.output_cost_per_1m

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def ensure_under_budget(self) -> None:
        if self.total_cost_usd > self.max_cost_usd:
            raise RuntimeError(
                f"AI budget exceeded: ${self.total_cost_usd:.4f} > ${self.max_cost_usd:.2f}"
            )
