from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(200))
    client_type: Mapped[str] = mapped_column(String(100))
    submitted_at: Mapped[str] = mapped_column(String(50))
    line_items_description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="RECEIVED")
    risk_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_value: Mapped[float | None] = mapped_column(Float, nullable=True)


class DecisionEvent(Base):
    __tablename__ = "decision_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(50), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    details_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), index=True)
    warehouse: Mapped[str] = mapped_column(String(30))
    stock: Mapped[float] = mapped_column(Float)
    ship_cost: Mapped[float] = mapped_column(Float, default=0)


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(250))
    unit_price: Mapped[float] = mapped_column(Float)
