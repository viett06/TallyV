"""HR-maintained sender routing and employee masters for configured mailbox intake."""

import csv
from io import StringIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.i18n import message
from app.core.serialization import model_dict
from app.crud import catalog as repository
from app.crud.outlook import get_connection
from app.models import Department, DepartmentSender, Employee
from app.schema.outlook import DepartmentUpdate


def workbook_template() -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    from app.core.attendance import HEADERS, SHEET_NAME

    workbook = Workbook()
    workbook.active.title = SHEET_NAME
    workbook.active.append(HEADERS)
    workbook.active.freeze_panes = "C2"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def update_department(db: Session, department_id: int, body: DepartmentUpdate) -> dict:
    department = repository.get_department(db, department_id)
    if not department:
        raise AppError(404, message("catalog.missing_department"))
    connection = get_connection(db, for_update=True)
    department.name = body.name
    existing = {sender.address: sender for sender in department.sender_addresses}
    department.sender_addresses = [
        existing.get(address) or DepartmentSender(address=address) for address in body.senders
    ]
    if connection:
        connection.delta_link = None  # Replay the recent window after changing the sender allowlist.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, message("catalog.conflict")) from None
    return {**model_dict(department), "senders": department.senders}


def create_department(db: Session, body: DepartmentUpdate) -> dict:
    connection = get_connection(db, for_update=True)
    department = Department(
        name=body.name, sender_addresses=[DepartmentSender(address=address) for address in body.senders]
    )
    db.add(department)
    if connection:
        connection.delta_link = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, message("catalog.conflict")) from None
    return {**model_dict(department), "senders": department.senders}


def import_employees(db: Session, content: bytes) -> dict:
    try:
        reader = csv.DictReader(StringIO(content.decode("utf-8-sig")))
        if set(reader.fieldnames or []) != {"employee_id", "name", "department_id"}:
            raise ValueError("Unexpected CSV headers")
        records, identifiers = [], set()
        for index, row in enumerate(reader):
            if index >= 2000 or None in row or any(value is None for value in row.values()):
                raise ValueError("Invalid CSV shape")
            employee_id, name, department_id = (
                row["employee_id"].strip(),
                row["name"].strip(),
                int(row["department_id"]),
            )
            if (
                not 1 <= len(employee_id) <= 30
                or not 1 <= len(name) <= 120
                or employee_id in identifiers
                or not repository.get_department(db, department_id)
            ):
                raise ValueError("Invalid employee record")
            identifiers.add(employee_id)
            existing = repository.get_employee(db, employee_id)
            if existing and (existing.name != name or existing.department_id != department_id):
                raise AppError(409, message("catalog.employee_conflict"))
            if existing is None:
                records.append(Employee(id=employee_id, name=name, department_id=department_id))
        if not identifiers:
            raise ValueError("CSV is empty")
    except (ValueError, UnicodeError, csv.Error, TypeError):
        raise AppError(422, message("catalog.invalid_csv")) from None
    db.add_all(records)
    db.commit()
    return {"imported": len(records)}
