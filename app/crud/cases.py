"""Case read models, version lookups and locks shared by review/export/dashboard."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisResult,
    Attachment,
    AttendanceCase,
    AuditLog,
    CaseVersion,
    Department,
    Email,
    EvidenceFile,
)
from app.schema.cases import CaseFilters


def case_query(filters: CaseFilters):
    query = (
        select(AttendanceCase, CaseVersion, AnalysisResult, Department, Email)
        .join(CaseVersion, AttendanceCase.active_version_id == CaseVersion.id)
        .join(AnalysisResult, AnalysisResult.version_id == CaseVersion.id)
        .join(Department, Department.id == AttendanceCase.department_id)
        .join(Attachment, Attachment.id == CaseVersion.attachment_id)
        .join(Email, Email.id == Attachment.email_id)
    )
    if filters.period:
        query = query.where(AttendanceCase.period_id == filters.period)
    if filters.source == "outlook":
        query = query.where(Email.source_id.startswith("outlook:"))
    elif filters.source == "mailpit":
        query = query.where(~Email.source_id.startswith("outlook:"))
    if filters.cycle == "unassigned":
        query = query.where(AttendanceCase.cycle_start.is_(None))
    elif filters.cycle:
        query = query.where(AttendanceCase.cycle_start == filters.cycle)
    if filters.department:
        query = query.where(AttendanceCase.department_id == int(filters.department))
    if filters.search:
        needle = "%" + filters.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(
                AttendanceCase.code.ilike(needle, escape="\\"),
                AttendanceCase.employee_id.ilike(needle, escape="\\"),
                CaseVersion.normalized["name"].as_string().ilike(needle, escape="\\"),
            )
        )
    if filters.category:
        query = query.where(AnalysisResult.status == "COMPLETED", AnalysisResult.category == filters.category)
    if filters.assessment:
        query = query.where(AnalysisResult.assessment == filters.assessment)
    if filters.hr_status:
        query = query.where(AttendanceCase.hr_status == filters.hr_status)
    return query


def list_rows(db: Session, filters: CaseFilters, *, ordered: bool = False):
    query = case_query(filters)
    if ordered:
        query = query.order_by(AttendanceCase.code)
    return db.execute(query).all()


def list_analysis_results(db: Session, filters: CaseFilters, *, for_update: bool = False) -> list[AnalysisResult]:
    case_ids = case_query(filters).with_only_columns(AttendanceCase.id)
    query = (
        select(AnalysisResult)
        .join(CaseVersion, CaseVersion.id == AnalysisResult.version_id)
        .where(CaseVersion.case_id.in_(case_ids), CaseVersion.status.in_(["ACTIVE", "PROPOSED"]))
        .order_by(AnalysisResult.id)
    )
    if for_update:
        query = query.with_for_update(of=AnalysisResult).execution_options(populate_existing=True)
    return list(db.scalars(query))


def paginate(db: Session, filters: CaseFilters, page: int, page_size: int, sort: str, direction: str):
    query = case_query(filters)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    columns = {
        "code": AttendanceCase.code,
        "employee": AttendanceCase.employee_id,
        "date": CaseVersion.normalized["date"].as_string(),
        "status": AttendanceCase.hr_status,
    }
    column = columns.get(sort, AttendanceCase.code)
    query = query.order_by(column.desc() if direction == "desc" else column.asc())
    return db.execute(query.offset((page - 1) * page_size).limit(page_size)).all(), total


def get_row(db: Session, case_id: int):
    return db.execute(case_query(CaseFilters(source="all")).where(AttendanceCase.id == case_id)).first()


def get_for_update(db: Session, case_id: int) -> AttendanceCase | None:
    return db.scalar(select(AttendanceCase).where(AttendanceCase.id == case_id).with_for_update())


def list_for_update(db: Session, ids: list[int] | None = None) -> list[AttendanceCase]:
    query = (
        select(AttendanceCase).order_by(AttendanceCase.id).with_for_update().execution_options(populate_existing=True)
    )
    if ids is not None:
        query = query.where(AttendanceCase.id.in_(ids))
    return list(db.scalars(query))


def get_analysis(db: Session, version_id: int) -> AnalysisResult | None:
    return db.scalar(select(AnalysisResult).where(AnalysisResult.version_id == version_id))


def get_version(db: Session, version_id: int) -> CaseVersion | None:
    return db.get(CaseVersion, version_id)


def list_versions(db: Session, case_id: int) -> list[CaseVersion]:
    return list(db.scalars(select(CaseVersion).where(CaseVersion.case_id == case_id).order_by(CaseVersion.id)))


def list_evidence(db: Session, version_id: int) -> list[EvidenceFile]:
    return list(db.scalars(select(EvidenceFile).where(EvidenceFile.version_id == version_id)))


def list_audit(db: Session, case_id: int) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.id.desc())))


def proposed_count(db: Session, case_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(CaseVersion)
        .where(CaseVersion.case_id == case_id, CaseVersion.status == "PROPOSED")
    )


def evidence_count(db: Session, version_id: int) -> int:
    return db.scalar(select(func.count()).select_from(EvidenceFile).where(EvidenceFile.version_id == version_id))
