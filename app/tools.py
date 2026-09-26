from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CatalogItem, Inventory


class FulfillmentTools:
    """Deterministic tools used by the agent."""

    def __init__(self, db: Session):
        self.db = db

    def search_catalog(self, text: str) -> list[CatalogItem]:
        return list(self.db.scalars(select(CatalogItem)))

    def check_inventory(self, sku: str, quantity: int, warehouse: str = "PRIMARY") -> dict:
        item = self.db.scalar(
            select(Inventory).where(
                Inventory.sku == sku,
                Inventory.warehouse == warehouse,
            )
        )

        if item is None:
            return {
                "sku": sku,
                "warehouse": warehouse,
                "available": False,
                "stock": 0,
                "requested": quantity,
                "reason": "SKU is not present in this warehouse.",
            }

        stock = max(0, item.stock)

        return {
            "sku": sku,
            "warehouse": warehouse,
            "available": stock >= quantity,
            "stock": stock,
            "requested": quantity,
            "reason": "Sufficient stock." if stock >= quantity else "Insufficient stock.",
        }

    def dispatch(self, sku: str, quantity: int, warehouse: str) -> dict:
        if quantity <= 0:
            raise ValueError("Dispatch quantity must be positive.")

        item = self.db.scalar(
            select(Inventory).where(
                Inventory.sku == sku,
                Inventory.warehouse == warehouse,
            )
        )

        if item is None or max(0, item.stock) < quantity:
            raise ValueError(f"Cannot dispatch {quantity} of {sku} from {warehouse}.")

        item.stock -= quantity
        self.db.commit()

        return {
            "action": "DISPATCHED",
            "sku": sku,
            "quantity": quantity,
            "warehouse": warehouse,
        }

    def reroute(self, sku: str, quantity: int) -> dict:
        """Reroute fulfillment to the alternate warehouse."""
        if quantity <= 0:
            raise ValueError("Reroute quantity must be positive.")

        item = self.db.scalar(
            select(Inventory).where(
                Inventory.sku == sku,
                Inventory.warehouse == "ALTERNATE",
            )
        )

        if item is None or max(0, item.stock) < quantity:
            raise ValueError(
                f"Cannot reroute {quantity} of {sku} from ALTERNATE."
            )

        item.stock -= quantity
        self.db.commit()

        return {
            "action": "ALTERNATE_REROUTE",
            "sku": sku,
            "quantity": quantity,
            "warehouse": "ALTERNATE",
            "reason": "Primary warehouse was insufficient; fulfillment rerouted to alternate warehouse.",
        }