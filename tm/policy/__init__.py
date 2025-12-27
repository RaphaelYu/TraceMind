# Policy adapters and clients (zero-conflict additions)

from .engine import PolicyEvaluator, PolicyEvaluationResult, PolicyViolation  # noqa: E402

__all__ = ["PolicyEvaluator", "PolicyEvaluationResult", "PolicyViolation"]
