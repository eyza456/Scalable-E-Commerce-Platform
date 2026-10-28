
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings


internal_key_header = APIKeyHeader(
    name="X-Internal-Service-Key",
    auto_error=False
)


def verify_internal_service(
    provided_key: str | None = Security(internal_key_header)
):
    if (
        not provided_key
        or not secrets.compare_digest(
            provided_key,
            settings.INTERNAL_SERVICE_KEY
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso interno no autorizado"
        )

    return True
