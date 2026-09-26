from .config import settings
from .schemas import LineDecision


def evaluate_order(
    client_type: str,
    total_value: float,
    line_decisions: list[LineDecision],
) -> tuple[str, str, bool, str]:
    if not line_decisions:
        return "PENDING_REVIEW", "HIGH", False, "Order has no valid line items."

    reasons = []

    if client_type.strip().lower() != "one-time order":
        reasons.append("client type is not the configured low-risk one-time order")

    if total_value > settings.auto_dispatch_max_total:
        reasons.append(
            f"order value {total_value:.2f} exceeds "
            f"auto-dispatch limit {settings.auto_dispatch_max_total:.2f}"
        )

    for line in line_decisions:
        if line.reconciliation_confidence < settings.min_reconciliation_confidence:
            reasons.append(f"low reconciliation confidence for '{line.raw_text}'")

        if line.decision not in {"PRIMARY_FULFILLMENT", "ALTERNATE_REROUTE"}:
            reasons.append(
                f"line '{line.raw_text}' requires {line.decision.lower().replace('_', ' ')}"
            )

    if reasons:
        return "PENDING_REVIEW", "HIGH", False, "; ".join(reasons)

    return "READY_TO_DISPATCH", "LOW", True, "All configured low-risk conditions passed."
