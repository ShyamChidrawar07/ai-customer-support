
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

#--------- Response schemas ----------
class ErrorDetails(BaseModel):
    field: str |None = None
    message: str

class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetails] = []
    request_id: str

class ErrorResponse(BaseModel):
    error: ErrorBody

# -----------Base exception classes ----------

class DomainError(Exception):
    status_code = 400
    code = "domain_error"
    message = "The request could not be completed."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or type(self).message
        super().__init__(self.message)

class NotFoundError(DomainError):
    status_code =  404
    code = "not_found"
    message = "Resource not found."

class ForbiddenError(DomainError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission."


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"
    message = "Resource conflict."


class InvalidTransitionError(ConflictError):
    code = "invalid_transition"
    message = "This status transition is not allowed."


# -----------3. AUTHENTICATION ERRORS--------------
class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_error"
    message = "Authentication is required."

class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    message = "Invalid email or password."

# -----------4. DATABASE ERRORS------------------

class DatabaseOperationError(Exception):
    status_code = 500
    code = "database_error"
    message = "A database operation failed."

    def __init__(self, message: str | None = None):
        self.message = message or type(self).message
        super().__init__(self.message)

#----------- 5. EXTERNAL SERVICE ERRORS--------------

class ExternalServiceError(Exception):
    status_code = 502
    code = "external_service_error"
    message = "An external service failed."

    def __init__(self, message: str | None = None):
        self.message = message or type(self).message
        super().__init__(self.message)

class ServiceTimeoutError(ExternalServiceError):
    status_code = 504
    code = "service_timeout"
    message = "An external service timed out."

# -------------Request ID--------------------

def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)

    if not request_id:
        request_id = f"req_{uuid4().hex[:12]}"
        request.state.request_id = request_id

    return request_id

#------------ 7. COMMON ERROR RESPONSE--------------

def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetails] | None = None,
) -> JSONResponse:

    request_id = get_request_id(request)

    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            request_id=request_id,
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )

#------- 8. DOMAIN ERROR HANDLER---------

async def domain_error_handler(
    request: Request,
    exc: DomainError,
) -> JSONResponse:

    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )

# --------9. VALIDATION ERROR HANDLER---------

async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:

    details = [
        ErrorDetails(
            field=".".join(str(part) for part in error["loc"]),
            message="Invalid or missing value.",
        )
        for error in exc.errors()
    ]

    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="The request contains invalid data.",
        details=details,
    )


# --------10. HTTP ERROR HANDLER---------

async def http_error_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:

    safe_errors = {
        400: ("bad_request", "The request is invalid."),
        401: ("unauthorized", "Authentication is required."),
        403: ("forbidden", "You do not have permission."),
        404: ("not_found", "Resource not found."),
        405: ("method_not_allowed", "This method is not allowed."),
        409: ("conflict", "Resource conflict."),
        429: ("rate_limited", "Too many requests."),
    }

    code, message = safe_errors.get(
        exc.status_code,
        ("http_error", "The request could not be completed."),
    )

    return error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
    )

# --------11. DATABASE ERROR HANDLER---------

async def database_error_handler(
    request: Request,
    exc: DatabaseOperationError,
) -> JSONResponse:

    logger.error(
        "Database operation failed. request_id=%s",
        get_request_id(request),
        exc_info=True,
    )

    return error_response(
        request,
        status_code=500,
        code=exc.code,
        message=exc.message,
    )

# --------12. EXTERNAL SERVICE ERROR HANDLER---------

async def external_service_error_handler(
    request: Request,
    exc: ExternalServiceError,
) -> JSONResponse:

    logger.warning(
        "External service failed. request_id=%s",
        get_request_id(request),
        exc_info=True,
    )

    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )

# --------13. UNEXPECTED ERROR HANDLER---------

async def unexpected_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:

    request_id = get_request_id(request)

    logger.error(
        "Unexpected error. request_id=%s",
        request_id,
        exc_info=(type(exc), exc, exc.__traceback__),
    )

    return error_response(
        request,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )

# --------14. REGISTER HANDLERS AND MIDDLEWARE-------

def register_exception_handlers(app: FastAPI) -> None:

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = f"req_{uuid4().hex[:12]}"

        response = await call_next(request)

        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.add_exception_handler(
        DomainError,
        domain_error_handler,
    )

    app.add_exception_handler(
        RequestValidationError,
        validation_error_handler,
    )

    app.add_exception_handler(
        StarletteHTTPException,
        http_error_handler,
    )

    app.add_exception_handler(
        DatabaseOperationError,
        database_error_handler,
    )

    app.add_exception_handler(
        ExternalServiceError,
        external_service_error_handler,
    )

    app.add_exception_handler(
        Exception,
        unexpected_error_handler,
    )

