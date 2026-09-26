import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CatalogItem, Inventory, Order


def ingest_csvs(db: Session, data_dir: str = "data") -> dict:
    base = Path(data_dir)

    catalog_path = base / "promo_merch_catalog.csv"
    orders_path = base / "promo_merch_orders.csv"
    alt_path = base / "alt_warehouse_inventory.csv"

    with catalog_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing = db.scalar(select(CatalogItem).where(CatalogItem.sku == row["sku"]))
            if existing:
                existing.name = row["name"]
                existing.unit_price = float(row["unit_price"])
            else:
                db.add(
                    CatalogItem(
                        sku=row["sku"],
                        name=row["name"],
                        unit_price=float(row["unit_price"]),
                    )
                )

            primary = db.scalar(
                select(Inventory).where(
                    Inventory.sku == row["sku"],
                    Inventory.warehouse == "PRIMARY",
                )
            )
            if primary:
                primary.stock = float(row["in_stock"])
            else:
                db.add(
                    Inventory(
                        sku=row["sku"],
                        warehouse="PRIMARY",
                        stock=float(row["in_stock"]),
                        ship_cost=0,
                    )
                )

    with alt_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing = db.scalar(
                select(Inventory).where(
                    Inventory.sku == row["sku"],
                    Inventory.warehouse == "ALTERNATE",
                )
            )
            if existing:
                existing.stock = float(row["alt_stock"])
                existing.ship_cost = float(row["ship_cost"])
            else:
                db.add(
                    Inventory(
                        sku=row["sku"],
                        warehouse="ALTERNATE",
                        stock=float(row["alt_stock"]),
                        ship_cost=float(row["ship_cost"]),
                    )
                )

    inserted = 0
    with orders_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing = db.scalar(select(Order).where(Order.order_id == row["order_id"]))
            if existing:
                continue

            db.add(
                Order(
                    order_id=row["order_id"],
                    client_name=row["client_name"],
                    client_type=row["client_type"],
                    submitted_at=row["submitted_at"],
                    line_items_description=row["line_items_description"],
                )
            )
            inserted += 1

    db.commit()
    return {
        "catalog_loaded": True,
        "alternate_inventory_loaded": True,
        "orders_inserted": inserted,
    }
