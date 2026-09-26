import json

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent import run_agent
from .db import SessionLocal, get_events, get_order, init_db, log_event
from .models import CatalogItem, Order
from .schemas import OverrideRequest
from .service import ingest_csvs
from .tools import FulfillmentTools

from pathlib import Path

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


app = FastAPI(
    title="Marketing-Souvenir Fulfillment Agent",
    version="1.0.0",
    description="Model/provider-agnostic agentic order reconciliation and fulfillment demo.",
)


@app.on_event("startup")
def startup():
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/ingest")
def ingest(db: Session = Depends(get_db)):
    try:
        return ingest_csvs(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/orders")
def list_orders(db: Session = Depends(get_db)):
    orders = list(db.scalars(select(Order).order_by(Order.id)))

    return [
        {
            "order_id": x.order_id,
            "client_name": x.client_name,
            "client_type": x.client_type,
            "status": x.status,
            "risk_level": x.risk_level,
            "total_value": x.total_value,
        }
        for x in orders
    ]


@app.post("/orders/{order_id}/process")
def process_order(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "DISPATCHED":
        raise HTTPException(
            status_code=409,
            detail="Order was already dispatched",
        )

    return run_agent(db, order).model_dump()


@app.post("/process-all")
def process_all(db: Session = Depends(get_db)):
    orders = list(db.scalars(select(Order).order_by(Order.id)))

    results = []

    for order in orders:
        if order.status != "DISPATCHED":
            results.append(run_agent(db, order).model_dump())

    return {
        "processed": len(results),
        "results": results,
    }


@app.get("/orders/{order_id}")
def order_details(order_id: str, db: Session = Depends(get_db)):
    order = get_order(db, order_id)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    events = get_events(db, order_id)

    return {
        "order": {
            "order_id": order.order_id,
            "client_name": order.client_name,
            "client_type": order.client_type,
            "line_items_description": order.line_items_description,
            "status": order.status,
            "risk_level": order.risk_level,
            "total_value": order.total_value,
            "decision_summary": order.decision_summary,
        },
        "decision_trace": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "details": json.loads(e.details_json),
                "created_at": e.created_at,
            }
            for e in events
        ],
    }


@app.post("/orders/{order_id}/override")
def override_order(
    order_id: str,
    request: OverrideRequest,
    db: Session = Depends(get_db),
):
    order = get_order(db, order_id)

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    decision = request.decision.upper().strip()

    if decision not in {"APPROVE", "REJECT"}:
        raise HTTPException(
            status_code=400,
            detail="decision must be APPROVE or REJECT",
        )

    # ============================================================
    # HUMAN REJECT
    # ============================================================

    if decision == "REJECT":
        order.status = "REJECTED"
        order.risk_level = "HUMAN_REJECTED"
        order.decision_summary = request.reason

        db.commit()

        log_event(
            db,
            order_id,
            "HUMAN_OVERRIDE",
            {
                "decision": decision,
                "reason": request.reason,
            },
        )

        db.commit()

        return {
            "order_id": order_id,
            "status": order.status,
            "override": decision,
            "reason": request.reason,
        }

    # ============================================================
    # HUMAN APPROVE
    # ============================================================

    # Get all persisted events.
    events = get_events(db, order_id)

    # ------------------------------------------------------------
    # Keep only the latest LINE_DECISION for every raw line.
    #
    # This is important because the agent can process the same
    # order multiple times. Older LINE_DECISION events may contain
    # stale reconciliation results.
    # ------------------------------------------------------------

    latest_line_events = {}

    for e in events:
        if e.event_type != "LINE_DECISION":
            continue

        details = json.loads(e.details_json)
        raw_text = details.get("raw_text")

        if not raw_text:
            continue

        existing = latest_line_events.get(raw_text)

        if existing is None or e.id > existing["_event_id"]:
            latest_line_events[raw_text] = {
                "_event_id": e.id,
                **details,
            }

    if not latest_line_events:
        raise HTTPException(
            status_code=409,
            detail="No persisted line decisions are available for approval.",
        )

    # ============================================================
    # HUMAN CATALOG CORRECTIONS
    # ============================================================

    #
    # Example request:
    #
    # {
    #   "decision": "APPROVE",
    #   "reason": "Human verified the product mapping.",
    #   "line_corrections": [
    #       {
    #           "raw_text": "10x Stress Ball - Branded",
    #           "sku": "PRM-123"
    #       }
    #   ]
    # }
    #
    # The SKU MUST exist in the catalog.
    # We never allow a human to introduce an arbitrary SKU.
    # ============================================================

    if request.line_corrections:

        catalog = list(db.scalars(select(CatalogItem)))

        for correction in request.line_corrections:

            # ----------------------------------------------------
            # 1. Verify SKU exists in our catalog
            # ----------------------------------------------------

            corrected_item = next(
                (
                    item
                    for item in catalog
                    if item.sku == correction.sku
                ),
                None,
            )

            if corrected_item is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"SKU '{correction.sku}' does not exist "
                        "in the catalog. Human correction cannot "
                        "introduce an unknown SKU."
                    ),
                )

            # ----------------------------------------------------
            # 2. Find the line that the human wants to correct
            # ----------------------------------------------------

            line = latest_line_events.get(correction.raw_text)

            if line is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Line '{correction.raw_text}' was not found "
                        "in the order."
                    ),
                )

            quantity = int(line["quantity"])

            # ----------------------------------------------------
            # 3. Check PRIMARY inventory again
            # ----------------------------------------------------

            tools = FulfillmentTools(db)

            primary = tools.check_inventory(
                corrected_item.sku,
                quantity,
                "PRIMARY",
            )

            log_event(
                db,
                order_id,
                "HUMAN_CATALOG_CORRECTION",
                {
                    "raw_text": correction.raw_text,
                    "old_sku": line.get("sku"),
                    "new_sku": corrected_item.sku,
                    "catalog_name": corrected_item.name,
                    "quantity": quantity,
                    "primary_inventory": primary,
                },
            )

            # ----------------------------------------------------
            # 4. PRIMARY can fulfill
            # ----------------------------------------------------

            if primary["available"]:

                line.update(
                    {
                        "sku": corrected_item.sku,
                        "catalog_name": corrected_item.name,
                        "reconciliation_confidence": 1.0,
                        "inventory_source": "PRIMARY",
                        "decision": "PRIMARY_FULFILLMENT",
                        "reason": (
                            "Human corrected the catalog mapping "
                            "and primary warehouse has sufficient stock."
                        ),
                    }
                )

            else:

                # ------------------------------------------------
                # 5. PRIMARY insufficient -> check ALTERNATE
                # ------------------------------------------------

                alternate = tools.check_inventory(
                    corrected_item.sku,
                    quantity,
                    "ALTERNATE",
                )

                log_event(
                    db,
                    order_id,
                    "HUMAN_CORRECTION_INVENTORY_CHECK",
                    {
                        "sku": corrected_item.sku,
                        "quantity": quantity,
                        "primary": primary,
                        "alternate": alternate,
                    },
                )

                # ------------------------------------------------
                # 6. ALTERNATE can fulfill
                # ------------------------------------------------

                if alternate["available"]:

                    line.update(
                        {
                            "sku": corrected_item.sku,
                            "catalog_name": corrected_item.name,
                            "reconciliation_confidence": 1.0,
                            "inventory_source": "ALTERNATE",
                            "decision": "ALTERNATE_REROUTE",
                            "reason": (
                                "Human corrected the catalog mapping; "
                                "primary warehouse is insufficient but "
                                "alternate warehouse can fulfill it."
                            ),
                        }
                    )

                # ------------------------------------------------
                # 7. Neither warehouse can fulfill
                # ------------------------------------------------

                else:

                    line.update(
                        {
                            "sku": corrected_item.sku,
                            "catalog_name": corrected_item.name,
                            "reconciliation_confidence": 1.0,
                            "inventory_source": "NONE",
                            "decision": "BACKORDER",
                            "reason": (
                                "Human corrected the catalog mapping, "
                                "but neither warehouse has sufficient stock."
                            ),
                        }
                    )

        # --------------------------------------------------------
        # Persist corrected LINE_DECISION events.
        #
        # We don't overwrite the old event. We create a new event
        # so the audit trail shows exactly what the human changed.
        # --------------------------------------------------------

        for line in latest_line_events.values():

            log_event(
                db,
                order_id,
                "LINE_DECISION",
                {
                    key: value
                    for key, value in line.items()
                    if key != "_event_id"
                },
            )

    # ============================================================
    # RE-CHECK ALL LINES AFTER HUMAN CORRECTIONS
    # ============================================================

    tools = FulfillmentTools(db)

    line_events = [
        {
            key: value
            for key, value in line.items()
            if key != "_event_id"
        }
        for line in latest_line_events.values()
    ]

    # ------------------------------------------------------------
    # Every line must now have a valid fulfillment decision.
    #
    # Human approval can bypass the RISK/POLICY restriction,
    # but cannot bypass:
    #
    #   - missing catalog mapping
    #   - backorder
    #   - insufficient inventory
    # ------------------------------------------------------------

    for line in line_events:

        if line["decision"] not in {
            "PRIMARY_FULFILLMENT",
            "ALTERNATE_REROUTE",
        }:

            raise HTTPException(
                status_code=409,
                detail=(
                    f"Line '{line['raw_text']}' is "
                    f"{line['decision']}. "
                    "It cannot be approved for dispatch. "
                    "Provide a valid catalog correction or resolve "
                    "the inventory issue first."
                ),
            )

        warehouse = (
            "ALTERNATE"
            if line["decision"] == "ALTERNATE_REROUTE"
            else "PRIMARY"
        )

        # --------------------------------------------------------
        # Final inventory check immediately before dispatch.
        # --------------------------------------------------------

        inventory = tools.check_inventory(
            line["sku"],
            int(line["quantity"]),
            warehouse,
        )

        if not inventory["available"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Inventory changed for {line['sku']}; "
                    "human approval cannot dispatch it safely."
                ),
            )

    # ============================================================
    # DISPATCH
    # ============================================================

    for line in line_events:

        warehouse = (
            "ALTERNATE"
            if line["decision"] == "ALTERNATE_REROUTE"
            else "PRIMARY"
        )

        result = tools.dispatch(
            line["sku"],
            int(line["quantity"]),
            warehouse,
        )

        log_event(
            db,
            order_id,
            "HUMAN_APPROVED_DISPATCH",
            result,
        )

    # ============================================================
    # UPDATE ORDER
    # ============================================================

    order.status = "DISPATCHED"
    order.risk_level = "HUMAN_APPROVED"
    order.decision_summary = (
        f"Human override approved: {request.reason}"
    )

    db.commit()

    # ============================================================
    # AUDIT LOG
    # ============================================================

    log_event(
        db,
        order_id,
        "HUMAN_OVERRIDE",
        {
            "decision": decision,
            "reason": request.reason,
            "line_corrections": [
                correction.model_dump()
                for correction in request.line_corrections
            ],
        },
    )

    db.commit()

    return {
        "order_id": order_id,
        "status": order.status,
        "override": decision,
        "reason": request.reason,
    }


# ================================================================
# STATIC UI
# ================================================================

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse(STATIC_DIR / "index.html")