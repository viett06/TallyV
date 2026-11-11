from fastapi import APIRouter

from app.api.deps import DBSession, HRUser
from app.schema.catalog import RuleView
from app.schema.common import OperationResult
from app.schema.rules import RuleCreateRequest, RuleUpdateRequest
from app.services import rules

router = APIRouter(prefix="/rules", tags=["Demo rules"])


@router.post("", response_model=RuleView, status_code=201)
def create(body: RuleCreateRequest, db: DBSession, user: HRUser):
    return rules.create_rule(db, body, user)


@router.put("/{category}", response_model=OperationResult)
def update(category: str, body: RuleUpdateRequest, db: DBSession, user: HRUser):
    return rules.update_rule(db, category, body, user)
