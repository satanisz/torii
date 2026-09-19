from http import HTTPStatus

from starlette.responses import JSONResponse

from torii_api.domain.errors import DomainError


def problem(error: DomainError, request_id: str) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "X-Request-ID": request_id}
    if error.status in {429, 503}:
        headers["Retry-After"] = "3"
    if error.status == 401:
        headers["WWW-Authenticate"] = 'Bearer realm="torii-api"'
    return JSONResponse(
        status_code=error.status,
        media_type="application/problem+json",
        headers=headers,
        content={
            "type": f"urn:torii:problem:{error.code}",
            "title": HTTPStatus(error.status).phrase,
            "status": error.status,
            "code": error.code,
            "request_id": request_id,
            "errors": [{"pointer": p, "code": "invalid"} for p in error.pointers[:100]],
        },
    )
