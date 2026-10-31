from sqlalchemy import text

from app.core.config import settings
from app.core.i18n import message
from app.crud import catalog as catalog_crud
from app.models import DemoRule, Department, DepartmentSender, Employee, User
from app.services.catalog import ensure_period
from app.services.review_calendar import business_today, payroll_period
from app.services.security import hash_password

DEPARTMENTS = [
    message("demo.department.internal_medicine"),
    message("demo.department.surgery"),
    message("demo.department.pediatrics"),
    message("demo.department.pharmacy"),
    message("demo.department.administration"),
]


def seed(db):
    if not catalog_crud.find_user(db, settings.demo_username):
        db.add(User(username=settings.demo_username, password_hash=hash_password(settings.demo_password)))
    for idx, name in enumerate(DEPARTMENTS, 1):
        if not catalog_crud.get_department(db, idx):
            db.add(
                Department(
                    id=idx, name=name, sender_addresses=[DepartmentSender(address=f"department{idx}@demo.invalid")]
                )
            )
    for month in range(1, 13):
        ensure_period(db, f"{payroll_period(business_today())[:4]}-{month:02}")
    db.flush()
    if db.get_bind().dialect.name == "postgresql":
        # Explicit demo IDs do not advance PostgreSQL's generated-ID sequence.
        db.execute(text("LOCK TABLE departments IN SHARE ROW EXCLUSIVE MODE"))
        db.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('departments', 'id'), "
                "GREATEST((SELECT MAX(id) FROM departments), (SELECT last_value FROM departments_id_seq)), true)"
            )
        )
    for idx in range(1, 41):
        code = f"MP{idx:03}"
        if not catalog_crud.get_employee(db, code):
            db.add(Employee(id=code, name=message("demo.employee_name", value0=idx), department_id=(idx - 1) // 8 + 1))
    for cat in ("FORGOT_CHECK", "DEVICE_ERROR", "LEAVE_NOT_RECORDED", "UNKNOWN"):
        if not catalog_crud.get_rule(db, cat):
            db.add(
                DemoRule(
                    category=cat,
                    settings={
                        "require_evidence": True,
                        "require_readable_ocr": True,
                        "require_shift": True,
                        "require_punch": cat in {"FORGOT_CHECK", "DEVICE_ERROR"},
                        "version": "demo-1.0",
                    },
                )
            )
    db.commit()
