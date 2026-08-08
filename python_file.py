
# app/utils/boa_error_handler.py

import logging
from typing import Dict, Any, Optional, Tuple
from enum import Enum

from .boa_api_service import BoAAuthenticationError, BoAAPIError, BoARateLimitError

logger = logging.getLogger(__name__)

class BoAErrorCode(Enum):
    """Standardized BoA API error codes"""
    AUTHENTICATION_FAILED = "AUTH_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    INVALID_CLIENT_ID = "INVALID_CLIENT_ID"
    INVALID_ACCESS_TOKEN = "INVALID_ACCESS_TOKEN"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    GATEWAY_TIMEOUT = "GATEWAY_TIMEOUT"
    BUSINESS_ERROR = "BUSINESS_ERROR"
    OPERATION_FAILED = "OPERATION_FAILED"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_ERROR = "UNKNOWN"

class BoAErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class BoAErrorHandler:
    """Comprehensive error handler for Bank of Abyssinia API responses"""

    # Error mapping based on BoA API documentation
    ERROR_MAPPINGS = {
        # Authentication errors (401)
        "Client ID is not found": (BoAErrorCode.INVALID_CLIENT_ID, BoAErrorSeverity.HIGH),
        "The access token is missing": (BoAErrorCode.INVALID_ACCESS_TOKEN, BoAErrorSeverity.HIGH),
        "invalid_request": (BoAErrorCode.AUTHORIZATION_FAILED, BoAErrorSeverity.HIGH),

        # Gateway timeout errors
        "Gateway timeout": (BoAErrorCode.GATEWAY_TIMEOUT, BoAErrorSeverity.CRITICAL),

        # Business/Operation errors
        "BUSINESS": (BoAErrorCode.BUSINESS_ERROR, BoAErrorSeverity.MEDIUM),
        "failed": (BoAErrorCode.OPERATION_FAILED, BoAErrorSeverity.MEDIUM),
    }

    @staticmethod
    def parse_boa_error(error_data: Dict[str, Any]) -> Tuple[BoAErrorCode, BoAErrorSeverity, str]:
        """
        Parse BoA API error response and return standardized error info
        """
        if not error_data:
            return BoAErrorCode.UNKNOWN_ERROR, BoAErrorSeverity.MEDIUM, "Unknown error occurred"

        # Check for authentication errors
        if error_data.get("status") == "401" or error_data.get("status") == 401:
            error_desc = error_data.get("errorDescription", "")
            if "Client ID" in error_desc:
                return BoAErrorCode.INVALID_CLIENT_ID, BoAErrorSeverity.HIGH, error_desc
            elif "access token" in error_desc.lower():
                return BoAErrorCode.INVALID_ACCESS_TOKEN, BoAErrorSeverity.HIGH, error_desc

        # Check for specific error messages
        error_message = error_data.get("error", "")
        if isinstance(error_message, dict):
            error_message = error_message.get("errorDetails", [{}])[0].get("message", "")

        for key_phrase, (error_code, severity) in BoAErrorHandler.ERROR_MAPPINGS.items():
            if key_phrase.lower() in error_message.lower() or key_phrase.lower() in str(error_data).lower():
                return error_code, severity, error_message or key_phrase

        # Check header status
        header = error_data.get("header", {})
        if isinstance(header, dict):
            header_status = header.get("status")
            if header_status == "failed":
                error_details = header.get("error", {})
                if error_details:
                    error_type = error_details.get("type")
                    if error_type == "BUSINESS":
                        return BoAErrorCode.BUSINESS_ERROR, BoAErrorSeverity.MEDIUM, error_details.get("errorDetails", [{}])[0].get("message", "Business error")

        # Default to operation failed for any other error
        return BoAErrorCode.OPERATION_FAILED, BoAErrorSeverity.MEDIUM, error_message or "Operation failed"

    @staticmethod
    def handle_boa_exception(exception: Exception) -> Dict[str, Any]:
        """
        Handle different types of BoA exceptions and return standardized response
        """
        if isinstance(exception, BoAAuthenticationError):
            error_code, severity, message = BoAErrorCode.AUTHENTICATION_FAILED, BoAErrorSeverity.HIGH, str(exception)
            logger.error(f"BoA Authentication Error: {message}")

        elif isinstance(exception, BoARateLimitError):
            error_code, severity, message = BoAErrorCode.RATE_LIMIT_EXCEEDED, BoAErrorSeverity.HIGH, str(exception)
            logger.warning(f"BoA Rate Limit Exceeded: {message}")

        elif isinstance(exception, BoAAPIError):
            # Try to parse the error response if available
            try:
                import json
                error_data = json.loads(str(exception).split(": ", 1)[-1] if ": " in str(exception) else "{}")
                error_code, severity, message = BoAErrorHandler.parse_boa_error(error_data)
            except:
                error_code, severity, message = BoAErrorCode.OPERATION_FAILED, BoAErrorSeverity.MEDIUM, str(exception)

            logger.error(f"BoA API Error: {message}")

        else:
            error_code, severity, message = BoAErrorCode.UNKNOWN_ERROR, BoAErrorSeverity.MEDIUM, str(exception)
            logger.error(f"BoA Unknown Error: {message}")

        return {
            "error_code": error_code.value,
            "severity": severity.value,
            "message": message,
            "timestamp": None,  # Will be set by caller
            "retryable": severity in [BoAErrorSeverity.LOW, BoAErrorSeverity.MEDIUM],
            "requires_admin_attention": severity in [BoAErrorSeverity.HIGH, BoAErrorSeverity.CRITICAL]
        }

    @staticmethod
    def create_error_response(error_code: BoAErrorCode, message: str, details: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Create standardized error response for API endpoints
        """
        return {
            "success": False,
            "error": {
                "code": error_code.value,
                "message": message,
                "details": details or {},
                "timestamp": None  # Will be set by caller
            }
        }

    @staticmethod
    def should_retry(error_code: BoAErrorCode, attempt_count: int = 1) -> bool:
        """
        Determine if an operation should be retried based on error code and attempt count
        """
        retryable_errors = [
            BoAErrorCode.NETWORK_ERROR,
            BoAErrorCode.GATEWAY_TIMEOUT,
            BoAErrorCode.RATE_LIMIT_EXCEEDED
        ]

        if error_code in retryable_errors and attempt_count < 3:
            return True

        if error_code == BoAErrorCode.OPERATION_FAILED and attempt_count < 2:
            return True

        return False

    @staticmethod
    def get_retry_delay_seconds(error_code: BoAErrorCode, attempt_count: int = 1) -> int:
        """
        Get delay in seconds before retrying based on error type and attempt count
        """
        base_delays = {
            BoAErrorCode.NETWORK_ERROR: 5,
            BoAErrorCode.GATEWAY_TIMEOUT: 10,
            BoAErrorCode.RATE_LIMIT_EXCEEDED: 30,
            BoAErrorCode.OPERATION_FAILED: 15
        }

        base_delay = base_delays.get(error_code, 10)
        # Exponential backoff
        return base_delay * (2 ** (attempt_count - 1))

    @staticmethod
    def log_error_context(operation: str, error_info: Dict[str, Any], additional_context: Optional[Dict] = None):
        """
        Log comprehensive error context for debugging and monitoring
        """
        context = {
            "operation": operation,
            "error_code": error_info.get("error_code"),
            "severity": error_info.get("severity"),
            "retryable": error_info.get("retryable"),
            "message": error_info.get("message")
        }

        if additional_context:
            context.update(additional_context)

        if error_info.get("severity") == BoAErrorSeverity.CRITICAL.value:
            logger.critical(f"BoA Critical Error in {operation}", extra=context)
        elif error_info.get("severity") == BoAErrorSeverity.HIGH.value:
            logger.error(f"BoA High Severity Error in {operation}", extra=context)
        elif error_info.get("severity") == BoAErrorSeverity.MEDIUM.value:
            logger.warning(f"BoA Medium Severity Error in {operation}", extra=context)
        else:
            logger.info(f"BoA Low Severity Error in {operation}", extra=context)

# Utility functions for common error scenarios

def handle_beneficiary_error(operation: str, account_id: str, error: Exception) -> Dict[str, Any]:
    """Handle errors in beneficiary operations"""
    error_info = BoAErrorHandler.handle_boa_exception(error)

    additional_context = {
        "operation_type": "beneficiary_lookup",
        "account_id": account_id[:4] + "****" if len(account_id) > 4 else "****",  # Mask account for logging
    }

    BoAErrorHandler.log_error_context(operation, error_info, additional_context)

    return BoAErrorHandler.create_error_response(
        BoAErrorCode.BUSINESS_ERROR,
        f"Beneficiary verification failed: {error_info['message']}"
    )

def handle_transfer_error(operation: str, transaction_id: str, error: Exception) -> Dict[str, Any]:
    """Handle errors in transfer operations"""
    error_info = BoAErrorHandler.handle_boa_exception(error)

    additional_context = {
        "operation_type": "transfer",
        "transaction_id": transaction_id,
    }

    BoAErrorHandler.log_error_context(operation, error_info, additional_context)

    return BoAErrorHandler.create_error_response(
        BoAErrorCode.OPERATION_FAILED,
        f"Transfer failed: {error_info['message']}"
    )

def handle_status_check_error(operation: str, transaction_id: str, error: Exception) -> Dict[str, Any]:
    """Handle errors in status check operations"""
    error_info = BoAErrorHandler.handle_boa_exception(error)

    additional_context = {
        "operation_type": "status_check",
        "transaction_id": transaction_id,
    }

    BoAErrorHandler.log_error_context(operation, error_info, additional_context)

    return BoAErrorHandler.create_error_response(
        BoAErrorCode.OPERATION_FAILED,
        f"Status check failed: {error_info['message']}"
    )
