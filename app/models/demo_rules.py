from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DemoRule(Base):
    __tablename__ = "demo_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(40), unique=True)
    settings: Mapped[dict] = mapped_column(JSON)
