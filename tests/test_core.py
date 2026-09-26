from app.policy import evaluate_order
from app.reconciler import find_catalog_match, normalize
from app.schemas import LineDecision


class Item:
    def __init__(self, sku, name):
        self.sku = sku
        self.name = name


def test_normalize():
    assert normalize("Polo Shirt - Navy") == "polo shirt navy"


def test_exact_catalog_match():
    result = find_catalog_match(
        "Polo Shirt - Navy",
        [Item("PRM-201", "Polo Shirt - Navy")],
    )
    assert result.sku == "PRM-201"
    assert result.confidence == 1.0


def test_low_risk_primary_order():
    lines = [
        LineDecision(
            raw_text="3x Polo Shirt - Navy",
            quantity=3,
            sku="PRM-201",
            catalog_name="Polo Shirt - Navy",
            reconciliation_confidence=0.99,
            inventory_source="PRIMARY",
            decision="PRIMARY_FULFILLMENT",
            reason="test",
        )
    ]

    status, risk, allowed, _ = evaluate_order("one-time order", 36, lines)

    assert status == "READY_TO_DISPATCH"
    assert risk == "LOW"
    assert allowed is True


def test_recurring_account_requires_review():
    lines = [
        LineDecision(
            raw_text="3x Polo Shirt - Navy",
            quantity=3,
            sku="PRM-201",
            catalog_name="Polo Shirt - Navy",
            reconciliation_confidence=0.99,
            inventory_source="PRIMARY",
            decision="PRIMARY_FULFILLMENT",
            reason="test",
        )
    ]

    status, risk, allowed, _ = evaluate_order(
        "recurring corporate account",
        36,
        lines,
    )

    assert status == "PENDING_REVIEW"
    assert allowed is False
