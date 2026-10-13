from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.kali_mcp import health
from app.models import User

router = APIRouter(prefix="/admin/kali", tags=["Kali MCP"])


@router.get("/health")
def kali_health(_: User = Depends(require_admin)):
    return health()
