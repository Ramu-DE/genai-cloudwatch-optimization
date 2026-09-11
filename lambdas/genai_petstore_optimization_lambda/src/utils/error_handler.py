"""
Error handling and categorization system for Luna Agent optimization testing.

This module provides comprehensive error categorization, logging, and monitoring
capabilities for the agent optimization framework.
"""

import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Categorization of error types for monitoring and analysis."""
    TOOL_FAILURE = "tool_failure"
    TOKEN_LIMIT = "token_limit"
    TIMEOUT = "timeout"
    LLM_ERROR = "llm_error"
    MEMORY_ERROR = "memory_error"
    DATABASE_ERROR = "database_error"
    VALIDATION_ERROR = "validation_error"
    CONFIGURATION_ERROR = "configuration_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Severity levels for error classification."""
    CRITICAL = "critical"  # System cannot continue
    HIGH = "high"  # Major functionality impaired
    MEDIUM = "medium"  # Degraded performance
    LOW = "low"  # Minor issue, system functional


@dataclass
class ErrorEvent:
    """Represents a single error occurrence with full context."""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    scenario_id: Optional[int] = None
    customer_id: Optional[str] = None
    session_id: Optional[str] = None
    execution_id: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    resolved: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error event to dictionary for logging/storage."""
        return {
            'error_type': self.error_type.value,
            'severity': self.severity.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'scenario_id': self.scenario_id,
            'customer_id': self.customer_id,
            'session_id': self.session_id,
            'execution_id': self.execution_id,
            'stack_trace': self.stack_trace,
            'context': self.context,
            'retry_count': self.retry_count,
            'resolved': self.resolved
        }


class ErrorCategorizer:
    """
    Categorizes exceptions into error types for monitoring and analysis.
    
    This class analyzes exception objects and their messages to determine
    the appropriate error category and severity level.
    """
    
    def __init__(self):
        self.error_patterns = {
            ErrorType.TOOL_FAILURE: [
                'tool', 'function call', 'invocation failed',
                'tool execution', 'tool not found'
            ],
            ErrorType.TOKEN_LIMIT: [
                'token limit', 'max tokens', 'context length',
                'too many tokens', 'token budget'
            ],
            ErrorType.TIMEOUT: [
                'timeout', 'timed out', 'deadline exceeded',
                'connection timeout', 'read timeout'
            ],
            ErrorType.LLM_ERROR: [
                'bedrock', 'model', 'inference', 'throttling',
                'rate limit', 'model error', 'llm'
            ],
            ErrorType.MEMORY_ERROR: [
                'memory', 'agentcore memory', 'memory service',
                'memory retrieval', 'memory storage'
            ],
            ErrorType.DATABASE_ERROR: [
                'dynamodb', 'database', 'query failed',
                'table', 'item not found', 'db'
            ],
            ErrorType.VALIDATION_ERROR: [
                'validation', 'invalid', 'malformed',
                'schema', 'required field'
            ],
            ErrorType.CONFIGURATION_ERROR: [
                'configuration', 'config', 'environment variable',
                'missing parameter', 'setup'
            ],
            ErrorType.NETWORK_ERROR: [
                'network', 'connection', 'socket',
                'dns', 'unreachable', 'connection refused'
            ]
        }
    
    def categorize(self, exception: Exception, context: Optional[Dict[str, Any]] = None) -> ErrorType:
        """
        Categorize an exception into an error type.
        
        Args:
            exception: The exception to categorize
            context: Optional context information
            
        Returns:
            ErrorType enum value
        """
        error_message = str(exception).lower()
        exception_type = type(exception).__name__.lower()
        
        # Check exception type first
        if 'timeout' in exception_type:
            return ErrorType.TIMEOUT
        if 'validation' in exception_type or 'value' in exception_type:
            return ErrorType.VALIDATION_ERROR
        
        # Check error message patterns
        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if pattern in error_message:
                    return error_type
        
        # Check context if provided
        if context:
            if context.get('tool_name'):
                return ErrorType.TOOL_FAILURE
            if context.get('token_count'):
                return ErrorType.TOKEN_LIMIT
        
        return ErrorType.UNKNOWN
    
    def determine_severity(self, error_type: ErrorType, exception: Exception) -> ErrorSeverity:
        """
        Determine the severity level of an error.
        
        Args:
            error_type: The categorized error type
            exception: The original exception
            
        Returns:
            ErrorSeverity enum value
        """
        # Critical errors that prevent system operation
        if error_type in [ErrorType.CONFIGURATION_ERROR, ErrorType.DATABASE_ERROR]:
            return ErrorSeverity.CRITICAL
        
        # High severity errors that significantly impact functionality
        if error_type in [ErrorType.LLM_ERROR, ErrorType.MEMORY_ERROR]:
            return ErrorSeverity.HIGH
        
        # Medium severity errors that cause degraded performance
        if error_type in [ErrorType.TOOL_FAILURE, ErrorType.TIMEOUT, ErrorType.TOKEN_LIMIT]:
            return ErrorSeverity.MEDIUM
        
        # Low severity errors that have minimal impact
        if error_type in [ErrorType.VALIDATION_ERROR, ErrorType.NETWORK_ERROR]:
            return ErrorSeverity.LOW
        
        return ErrorSeverity.MEDIUM


class ErrorLogger:
    """
    Centralized error logging with categorization and CloudWatch integration.
    
    This class provides structured error logging with automatic categorization,
    CloudWatch metrics emission, and error pattern tracking.
    """
    
    def __init__(self, enable_cloudwatch: bool = False):
        """
        Initialize error logger.
        
        Args:
            enable_cloudwatch: Whether to emit CloudWatch metrics (requires boto3)
        """
        self.categorizer = ErrorCategorizer()
        self.enable_cloudwatch = enable_cloudwatch
        self.cloudwatch_client = None
        
        if enable_cloudwatch:
            try:
                import boto3
                self.cloudwatch_client = boto3.client('cloudwatch')
            except Exception as e:
                logger.warning(f"Could not initialize CloudWatch client: {e}")
                self.enable_cloudwatch = False
    
    def log_error(
        self,
        exception: Exception,
        scenario_id: Optional[int] = None,
        customer_id: Optional[str] = None,
        session_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> ErrorEvent:
        """
        Log an error with full categorization and context.
        
        Args:
            exception: The exception that occurred
            scenario_id: Optional scenario identifier
            customer_id: Optional customer identifier
            session_id: Optional session identifier
            execution_id: Optional execution identifier
            context: Optional additional context
            retry_count: Number of retry attempts
            
        Returns:
            ErrorEvent object with full error details
        """
        # Categorize the error
        error_type = self.categorizer.categorize(exception, context)
        severity = self.categorizer.determine_severity(error_type, exception)
        
        # Get stack trace
        import traceback
        stack_trace = traceback.format_exc()
        
        # Create error event
        error_event = ErrorEvent(
            error_type=error_type,
            severity=severity,
            message=str(exception),
            scenario_id=scenario_id,
            customer_id=customer_id,
            session_id=session_id,
            execution_id=execution_id,
            stack_trace=stack_trace,
            context=context or {},
            retry_count=retry_count
        )
        
        # Log to standard logger
        log_level = self._get_log_level(severity)
        logger.log(
            log_level,
            f"[{error_type.value.upper()}] {severity.value.upper()}: {exception}",
            extra={
                'error_event': error_event.to_dict(),
                'scenario_id': scenario_id,
                'error_type': error_type.value,
                'severity': severity.value
            }
        )
        
        # Emit CloudWatch metric
        if self.enable_cloudwatch:
            self._emit_cloudwatch_metric(error_event)
        
        return error_event
    
    def _get_log_level(self, severity: ErrorSeverity) -> int:
        """Map severity to logging level."""
        severity_map = {
            ErrorSeverity.CRITICAL: logging.CRITICAL,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.LOW: logging.INFO
        }
        return severity_map.get(severity, logging.WARNING)
    
    def _emit_cloudwatch_metric(self, error_event: ErrorEvent):
        """
        Emit error metric to CloudWatch.
        
        Args:
            error_event: The error event to emit
        """
        if not self.cloudwatch_client:
            return
        
        try:
            dimensions = [
                {'Name': 'ErrorType', 'Value': error_event.error_type.value},
                {'Name': 'Severity', 'Value': error_event.severity.value}
            ]
            
            if error_event.scenario_id:
                dimensions.append({
                    'Name': 'ScenarioId',
                    'Value': str(error_event.scenario_id)
                })
            
            self.cloudwatch_client.put_metric_data(
                Namespace='LunaAgent/Optimization',
                MetricData=[
                    {
                        'MetricName': 'ErrorCount',
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': error_event.timestamp,
                        'Dimensions': dimensions
                    }
                ]
            )
            
            logger.debug(f"Emitted CloudWatch metric for {error_event.error_type.value}")
            
        except Exception as e:
            logger.warning(f"Failed to emit CloudWatch metric: {e}")


# Global error logger instance
_error_logger: Optional[ErrorLogger] = None


def get_error_logger(enable_cloudwatch: bool = False) -> ErrorLogger:
    """
    Get or create the global error logger instance.
    
    Args:
        enable_cloudwatch: Whether to enable CloudWatch metrics
        
    Returns:
        ErrorLogger instance
    """
    global _error_logger
    if _error_logger is None:
        _error_logger = ErrorLogger(enable_cloudwatch=enable_cloudwatch)
    return _error_logger


def log_error(
    exception: Exception,
    scenario_id: Optional[int] = None,
    customer_id: Optional[str] = None,
    session_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    retry_count: int = 0,
    enable_cloudwatch: bool = False
) -> ErrorEvent:
    """
    Convenience function to log an error using the global error logger.
    
    Args:
        exception: The exception that occurred
        scenario_id: Optional scenario identifier
        customer_id: Optional customer identifier
        session_id: Optional session identifier
        execution_id: Optional execution identifier
        context: Optional additional context
        retry_count: Number of retry attempts
        enable_cloudwatch: Whether to enable CloudWatch metrics
        
    Returns:
        ErrorEvent object with full error details
    """
    error_logger = get_error_logger(enable_cloudwatch=enable_cloudwatch)
    return error_logger.log_error(
        exception=exception,
        scenario_id=scenario_id,
        customer_id=customer_id,
        session_id=session_id,
        execution_id=execution_id,
        context=context,
        retry_count=retry_count
    )
