from fastapi import APIRouter, Depends, Query

from core.security import get_current_user
from services.permissions import check_business_access
from services.reports import build

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("")
def reports(business_id: str, days: int = Query(90, ge=7, le=730), user_id: str = Depends(get_current_user)):
    check_business_access(user_id, business_id)
    return build(business_id, days)
