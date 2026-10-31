from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.api.deps import DBSession, Filters, HRUser
from app.core.errors import AppError
from app.core.i18n import message
from app.schema.catalog import BootstrapView, DashboardView, DepartmentView
from app.schema.outlook import DepartmentUpdate, EmployeeImportResult
from app.services import catalog, mail_catalog

router = APIRouter(tags=["Catalogue & dashboard"])


@router.get("/bootstrap", response_model=BootstrapView)
def bootstrap(db: DBSession, user: HRUser):
    return catalog.bootstrap(db)


@router.get("/dashboard", response_model=DashboardView)
def dashboard(db: DBSession, selection: Filters, user: HRUser):
    return catalog.dashboard(db, selection)


@router.put("/departments/{department_id}", response_model=DepartmentView)
def update_department(department_id: int, body: DepartmentUpdate, db: DBSession, user: HRUser):
    return mail_catalog.update_department(db, department_id, body)


@router.post("/departments", response_model=DepartmentView)
def create_department(body: DepartmentUpdate, db: DBSession, user: HRUser):
    return mail_catalog.create_department(db, body)


@router.get("/employees/template")
def employee_template(user: HRUser):
    return Response(
        "\ufeffemployee_id,name,department_id\r\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="employees-template.csv"'},
    )


@router.get("/workbooks/template")
def workbook_template(user: HRUser):
    return Response(
        mail_catalog.workbook_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="attendance-template.xlsx"'},
    )


@router.post("/employees/import", response_model=EmployeeImportResult)
async def import_employees(request: Request, db: DBSession, user: HRUser):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 1024 * 1024:
            raise AppError(413, message("catalog.invalid_csv"))
    return mail_catalog.import_employees(db, bytes(content))
