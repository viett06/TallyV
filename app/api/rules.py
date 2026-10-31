from fastapi import APIRouter

from app.api.deps import DBSession, HRUser
from app.schema.common import OperationResult
from app.schema.rules import RuleUpdateRequest
from app.services import rules

router = APIRouter(prefix="/rules", tags=["Demo rules"])


@router.put("/{category}", response_model=OperationResult)
def update(category: str, body: RuleUpdateRequest, db: DBSession, user: HRUser):
    return rules.update_rule(db, category, body, user)
