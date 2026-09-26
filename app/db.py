import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base, DecisionEvent, Order

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def log_event(db: Session, order_id: str, event_type: str, details: dict) -> None:
    db.add(
        DecisionEvent(
            order_id=order_id,
            event_type=event_type,
            details_json=json.dumps(details, default=str),
        )
    )
    db.commit()


def get_order(db: Session, order_id: str):
    return db.scalar(select(Order).where(Order.order_id == order_id))


def get_events(db: Session, order_id: str):
    return list(
        db.scalars(
            select(DecisionEvent)
            .where(DecisionEvent.order_id == order_id)
            .order_by(DecisionEvent.id)
        )
    )
