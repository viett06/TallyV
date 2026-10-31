from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DemoRule, Department, DepartmentSender, Employee, ReviewPeriod, User


def list_departments(db: Session) -> list[Department]:
    return list(db.scalars(select(Department).order_by(Department.id)))


def list_periods(db: Session) -> list[ReviewPeriod]:
    return list(db.scalars(select(ReviewPeriod).order_by(ReviewPeriod.id.desc())))


def list_rules(db: Session) -> list[DemoRule]:
    return list(db.scalars(select(DemoRule)))


def get_rule(db: Session, category: str, *, for_update: bool = False) -> DemoRule | None:
    query = select(DemoRule).where(DemoRule.category == category)
    return db.scalar(query.with_for_update() if for_update else query)


def get_department(db: Session, department_id: int) -> Department | None:
    return db.get(Department, department_id)


def get_employee(db: Session, employee_id: str) -> Employee | None:
    return db.get(Employee, employee_id)


def get_period(db: Session, period_id: str) -> ReviewPeriod | None:
    return db.get(ReviewPeriod, period_id)


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def departments_by_sender(db: Session, sender: str) -> list[Department]:
    return list(
        db.scalars(select(Department).join(DepartmentSender).where(DepartmentSender.address == sender.strip().lower()))
    )


def find_department_by_sender(db: Session, sender: str, department_name: str | None = None) -> Department | None:
    matches = departments_by_sender(db, sender)
    if len(matches) == 1:
        return matches[0]
    return next((department for department in matches if department.name == department_name), None)
