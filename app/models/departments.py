from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sender_addresses: Mapped[list["DepartmentSender"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="DepartmentSender.address"
    )

    @property
    def senders(self) -> list[str]:
        return [sender.address for sender in self.sender_addresses]


class DepartmentSender(Base):
    __tablename__ = "department_senders"
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True)
    address: Mapped[str] = mapped_column(String(200), primary_key=True, index=True)
