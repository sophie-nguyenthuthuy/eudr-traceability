"""Domain exceptions surfaced as RFC 7807 problem details by the API layer."""

from __future__ import annotations


class EUDRError(Exception):
    """Base for all domain errors. Maps to 4xx by default."""

    status_code: int = 400
    code: str = "eudr_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(EUDRError):
    status_code = 404
    code = "not_found"


class ConflictError(EUDRError):
    status_code = 409
    code = "conflict"


class AuthError(EUDRError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(EUDRError):
    status_code = 403
    code = "forbidden"


class ValidationError(EUDRError):
    status_code = 422
    code = "validation_failed"


class DeforestationRiskError(EUDRError):
    """Plot fails the EUDR cutoff-date deforestation check."""

    status_code = 422
    code = "deforestation_risk"


class TracesNTError(EUDRError):
    """EU TRACES NT submission failed (permanent — typically a 4xx).

    Raised when TRACES NT actively rejects the DDS. Not retried — fix the
    payload and resubmit.
    """

    status_code = 502
    code = "traces_nt_unavailable"


class TracesNTRetryableError(TracesNTError):
    """Transient TRACES NT failure (5xx or transport error) — safe to retry."""

    code = "traces_nt_retryable"
