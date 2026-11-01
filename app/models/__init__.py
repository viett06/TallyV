"""ORM model registry. All classes share app.db.base.Base."""

from app.models.analysis_results import AnalysisResult
from app.models.attachments import Attachment
from app.models.attendance_cases import AttendanceCase
from app.models.audit_logs import AuditLog
from app.models.case_versions import CaseVersion
from app.models.demo_rules import DemoRule
from app.models.departments import Department, DepartmentSender
from app.models.emails import Email
from app.models.employees import Employee
from app.models.evidence_files import EvidenceFile
from app.models.hr_submissions import HrSubmission
from app.models.import_batches import ImportBatch
from app.models.mock_hr import MockHrAttendance, MockHrReceipt
from app.models.outlook_connections import OutlookAuthFlow, OutlookConnection
from app.models.processing_jobs import ProcessingJob
from app.models.review_periods import ReviewPeriod
from app.models.users import User

__all__ = [
    "User",
    "Department",
    "DepartmentSender",
    "Employee",
    "ReviewPeriod",
    "Email",
    "Attachment",
    "ImportBatch",
    "AttendanceCase",
    "CaseVersion",
    "EvidenceFile",
    "AnalysisResult",
    "AuditLog",
    "ProcessingJob",
    "DemoRule",
    "OutlookConnection",
    "OutlookAuthFlow",
    "HrSubmission",
    "MockHrAttendance",
    "MockHrReceipt",
]
