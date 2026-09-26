import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import log_event
from .llm import build_llm_client
from .models import CatalogItem, Order
from .policy import evaluate_order
from .schemas import LineDecision, OrderDecision
from .tools import FulfillmentTools


def split_lines(value: str) -> list[str]:
    if not value or not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def run_agent(db: Session, order: Order) -> OrderDecision:
    tools = FulfillmentTools(db)
    llm = build_llm_client()

    catalog = list(db.scalars(select(CatalogItem)))
    catalog_names = [x.name for x in catalog]

    log_event(db, order.order_id, "AGENT_STARTED", {"client_type": order.client_type})

    line_decisions: list[LineDecision] = []
    actions: list[dict] = []

    for line_text in split_lines(order.line_items_description):
        try:
            interpretation = llm.interpret_line(line_text, catalog_names)
            log_event(
                db,
                order.order_id,
                "LLM_INTERPRETATION",
                interpretation.model_dump(),
            )
        except Exception as exc:
            interpretation = None
            log_event(
                db,
                order.order_id,
                "LLM_ERROR",
                {"error": str(exc), "line": line_text},
            )

        quantity = interpretation.quantity if interpretation else 0

        match = re.match(r"\s*(\d+)\s*x\s*(.+?)\s*$", line_text, re.IGNORECASE)
        if match:
            quantity = int(match.group(1))
            product_text = match.group(2).strip()
        else:
            product_text = line_text

        if quantity <= 0:
            line_decisions.append(
                LineDecision(
                    raw_text=line_text,
                    quantity=max(quantity, 0),
                    sku=None,
                    catalog_name=None,
                    reconciliation_confidence=0,
                    inventory_source="NONE",
                    decision="INVALID_LINE",
                    reason="Quantity could not be validated as a positive integer.",
                )
            )
            continue

        from .reconciler import find_catalog_match

        catalog_match = find_catalog_match(product_text, catalog)

        # If the LLM proposes a SKU, accept it only if that SKU exists in our catalog.
        if interpretation and interpretation.sku:
            known = next((x for x in catalog if x.sku == interpretation.sku), None)
            if known:
                catalog_match.sku = known.sku
                catalog_match.name = known.name
                catalog_match.confidence = min(
                    catalog_match.confidence or 1.0,
                    interpretation.confidence,
                )
                catalog_match.match_type = "llm_validated"

        log_event(
            db,
            order.order_id,
            "CATALOG_RECONCILIATION",
            {
                "line": line_text,
                "product_text": product_text,
                **catalog_match.model_dump(),
            },
        )

        if not catalog_match.sku:

            if catalog_match.match_type == "ambiguous":
                decision = "AMBIGUOUS_MATCH"
                reason = catalog_match.reason

            elif catalog_match.match_type in {
                "no_confident_match",
                "no_catalog",
            }:
                decision = "NO_CATALOG_MATCH"
                reason = catalog_match.reason

            else:
                decision = "AMBIGUOUS_MATCH"
                reason = catalog_match.reason

            line_decisions.append(
                LineDecision(
                    raw_text=line_text,
                    quantity=quantity,
                    sku=None,
                    catalog_name=None,
                    reconciliation_confidence=catalog_match.confidence,
                    inventory_source="NONE",
                    decision=decision,
                    reason=reason,
                )
            )

            continue

        primary = tools.check_inventory(catalog_match.sku, quantity, "PRIMARY")
        log_event(db, order.order_id, "PRIMARY_INVENTORY_CHECK", primary)

        if primary["available"]:
            line_decisions.append(
                LineDecision(
                    raw_text=line_text,
                    quantity=quantity,
                    sku=catalog_match.sku,
                    catalog_name=catalog_match.name,
                    reconciliation_confidence=catalog_match.confidence,
                    inventory_source="PRIMARY",
                    decision="PRIMARY_FULFILLMENT",
                    reason="Primary warehouse has sufficient stock.",
                )
            )
            continue

        alternate = tools.check_inventory(catalog_match.sku, quantity, "ALTERNATE")
        log_event(db, order.order_id, "ALTERNATE_INVENTORY_CHECK", alternate)

        if alternate["available"]:
            line_decisions.append(
                LineDecision(
                    raw_text=line_text,
                    quantity=quantity,
                    sku=catalog_match.sku,
                    catalog_name=catalog_match.name,
                    reconciliation_confidence=catalog_match.confidence,
                    inventory_source="ALTERNATE",
                    decision="ALTERNATE_REROUTE",
                    reason="Primary warehouse is insufficient; alternate warehouse can fulfill the line.",
                )
            )
        else:
            line_decisions.append(
                LineDecision(
                    raw_text=line_text,
                    quantity=quantity,
                    sku=catalog_match.sku,
                    catalog_name=catalog_match.name,
                    reconciliation_confidence=catalog_match.confidence,
                    inventory_source="NONE",
                    decision="BACKORDER",
                    reason="Neither primary nor alternate warehouse has sufficient stock.",
                )
            )

    # Persist the per-line decision so a human can review/approve it later.
    for line in line_decisions:
        log_event(
            db,
            order.order_id,
            "LINE_DECISION",
            line.model_dump(),
        )

    price_by_sku = {x.sku: x.unit_price for x in catalog}
    total_value = sum(
        line.quantity * price_by_sku.get(line.sku, 0)
        for line in line_decisions
        if line.sku
    )

    status, risk, auto_dispatch, policy_reason = evaluate_order(
        order.client_type,
        total_value,
        line_decisions,
    )

    policy_action = {
        "action": "POLICY_DECISION",
        "status": status,
        "risk_level": risk,
        "auto_dispatch_allowed": auto_dispatch,
        "reason": policy_reason,
    }
    actions.append(policy_action)
    log_event(db, order.order_id, "POLICY_DECISION", policy_action)

    # Critical safety rule: only PRIMARY_FULFILLMENT can be automatically dispatched.
    if auto_dispatch:
        for line in line_decisions:
            result = tools.dispatch(line.sku, line.quantity, "PRIMARY")
            actions.append(result)
            log_event(db, order.order_id, "DISPATCH", result)

        order.status = "DISPATCHED"
        summary = "Low-risk order automatically dispatched from primary warehouse."
    else:
        order.status = "PENDING_REVIEW"
        summary = f"Human review required: {policy_reason}"

    order.risk_level = risk
    order.total_value = total_value
    order.decision_summary = summary
    db.commit()

    log_event(
        db,
        order.order_id,
        "AGENT_FINISHED",
        {"status": order.status, "summary": summary},
    )

    return OrderDecision(
        order_id=order.order_id,
        status=order.status,
        risk_level=risk,
        auto_dispatch_allowed=auto_dispatch,
        total_value=total_value,
        line_decisions=line_decisions,
        actions=actions,
        review_required=not auto_dispatch,
        summary=summary,
    )
