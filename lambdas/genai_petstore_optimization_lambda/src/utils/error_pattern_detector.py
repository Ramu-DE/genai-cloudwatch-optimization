"""
Error pattern detection and analysis for Luna Agent optimization testing.

This module tracks error frequency over time, identifies common patterns,
and generates recommendations for error handling improvements.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass, field
import json

from .error_handler import ErrorEvent, ErrorType, ErrorSeverity

logger = logging.getLogger(__name__)


@dataclass
class ErrorPattern:
    """Represents a detected error pattern."""
    error_type: ErrorType
    frequency: int
    first_occurrence: datetime
    last_occurrence: datetime
    affected_scenarios: List[int] = field(default_factory=list)
    common_messages: List[str] = field(default_factory=list)
    severity_distribution: Dict[str, int] = field(default_factory=dict)
    retry_success_rate: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert pattern to dictionary."""
        return {
            'error_type': self.error_type.value,
            'frequency': self.frequency,
            'first_occurrence': self.first_occurrence.isoformat(),
            'last_occurrence': self.last_occurrence.isoformat(),
            'affected_scenarios': self.affected_scenarios,
            'common_messages': self.common_messages,
            'severity_distribution': self.severity_distribution,
            'retry_success_rate': self.retry_success_rate
        }


@dataclass
class ErrorRecommendation:
    """Represents a recommendation for error handling improvement."""
    error_type: ErrorType
    priority: str  # 'high', 'medium', 'low'
    recommendation: str
    rationale: str
    estimated_impact: str
    
    def to_dict(self) -> Dict:
        """Convert recommendation to dictionary."""
        return {
            'error_type': self.error_type.value,
            'priority': self.priority,
            'recommendation': self.recommendation,
            'rationale': self.rationale,
            'estimated_impact': self.estimated_impact
        }


class ErrorPatternDetector:
    """
    Detects patterns in error occurrences and generates recommendations.
    
    This class maintains a history of error events and analyzes them to:
    - Track error frequency over time
    - Identify most common error patterns
    - Calculate retry success rates
    - Generate actionable recommendations
    """
    
    def __init__(self, max_history_size: int = 1000):
        """
        Initialize error pattern detector.
        
        Args:
            max_history_size: Maximum number of error events to keep in memory
        """
        self.error_history: List[ErrorEvent] = []
        self.max_history_size = max_history_size
        self.patterns: Dict[ErrorType, ErrorPattern] = {}
    
    def add_error(self, error_event: ErrorEvent):
        """
        Add an error event to the history and update patterns.
        
        Args:
            error_event: The error event to add
        """
        # Add to history
        self.error_history.append(error_event)
        
        # Maintain max history size
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size:]
        
        # Update patterns
        self._update_patterns()
    
    def _update_patterns(self):
        """Update error patterns based on current history."""
        # Group errors by type
        errors_by_type: Dict[ErrorType, List[ErrorEvent]] = defaultdict(list)
        for error in self.error_history:
            errors_by_type[error.error_type].append(error)
        
        # Analyze each error type
        for error_type, events in errors_by_type.items():
            if not events:
                continue
            
            # Calculate frequency
            frequency = len(events)
            
            # Get time range
            timestamps = [e.timestamp for e in events]
            first_occurrence = min(timestamps)
            last_occurrence = max(timestamps)
            
            # Get affected scenarios
            affected_scenarios = list(set(
                e.scenario_id for e in events if e.scenario_id is not None
            ))
            
            # Get common messages (top 5)
            message_counter = Counter(e.message for e in events)
            common_messages = [msg for msg, _ in message_counter.most_common(5)]
            
            # Calculate severity distribution
            severity_counter = Counter(e.severity.value for e in events)
            severity_distribution = dict(severity_counter)
            
            # Calculate retry success rate
            retry_events = [e for e in events if e.retry_count > 0]
            resolved_retries = [e for e in retry_events if e.resolved]
            retry_success_rate = (
                len(resolved_retries) / len(retry_events)
                if retry_events else 0.0
            )
            
            # Create or update pattern
            self.patterns[error_type] = ErrorPattern(
                error_type=error_type,
                frequency=frequency,
                first_occurrence=first_occurrence,
                last_occurrence=last_occurrence,
                affected_scenarios=affected_scenarios,
                common_messages=common_messages,
                severity_distribution=severity_distribution,
                retry_success_rate=retry_success_rate
            )
    
    def get_error_frequency(
        self,
        time_window: Optional[timedelta] = None,
        error_type: Optional[ErrorType] = None
    ) -> Dict[ErrorType, int]:
        """
        Get error frequency within a time window.
        
        Args:
            time_window: Optional time window (defaults to all time)
            error_type: Optional filter by error type
            
        Returns:
            Dictionary mapping error types to frequency counts
        """
        # Filter by time window
        if time_window:
            cutoff_time = datetime.utcnow() - time_window
            filtered_errors = [
                e for e in self.error_history
                if e.timestamp >= cutoff_time
            ]
        else:
            filtered_errors = self.error_history
        
        # Filter by error type
        if error_type:
            filtered_errors = [
                e for e in filtered_errors
                if e.error_type == error_type
            ]
        
        # Count by type
        frequency = Counter(e.error_type for e in filtered_errors)
        return dict(frequency)
    
    def get_most_common_patterns(self, top_n: int = 5) -> List[ErrorPattern]:
        """
        Get the most common error patterns.
        
        Args:
            top_n: Number of top patterns to return
            
        Returns:
            List of ErrorPattern objects sorted by frequency
        """
        sorted_patterns = sorted(
            self.patterns.values(),
            key=lambda p: p.frequency,
            reverse=True
        )
        return sorted_patterns[:top_n]
    
    def get_error_rate_trend(
        self,
        time_buckets: int = 10,
        error_type: Optional[ErrorType] = None
    ) -> List[Tuple[datetime, int]]:
        """
        Get error rate trend over time.
        
        Args:
            time_buckets: Number of time buckets to divide history into
            error_type: Optional filter by error type
            
        Returns:
            List of (timestamp, count) tuples
        """
        if not self.error_history:
            return []
        
        # Filter by error type
        filtered_errors = self.error_history
        if error_type:
            filtered_errors = [
                e for e in filtered_errors
                if e.error_type == error_type
            ]
        
        if not filtered_errors:
            return []
        
        # Get time range
        timestamps = [e.timestamp for e in filtered_errors]
        min_time = min(timestamps)
        max_time = max(timestamps)
        time_range = (max_time - min_time).total_seconds()
        
        if time_range == 0:
            return [(min_time, len(filtered_errors))]
        
        # Create time buckets
        bucket_size = time_range / time_buckets
        buckets: Dict[int, int] = defaultdict(int)
        
        for error in filtered_errors:
            bucket_index = int(
                (error.timestamp - min_time).total_seconds() / bucket_size
            )
            buckets[bucket_index] += 1
        
        # Convert to list of tuples
        trend = []
        for i in range(time_buckets):
            bucket_time = min_time + timedelta(seconds=i * bucket_size)
            count = buckets.get(i, 0)
            trend.append((bucket_time, count))
        
        return trend
    
    def generate_recommendations(self) -> List[ErrorRecommendation]:
        """
        Generate recommendations for error handling improvements.
        
        Returns:
            List of ErrorRecommendation objects
        """
        recommendations = []
        
        # Get most common patterns
        common_patterns = self.get_most_common_patterns(top_n=10)
        
        for pattern in common_patterns:
            # Determine priority based on frequency and severity
            priority = self._determine_priority(pattern)
            
            # Generate recommendation based on error type
            recommendation = self._generate_recommendation_for_type(pattern)
            
            if recommendation:
                recommendations.append(recommendation)
        
        return recommendations
    
    def _determine_priority(self, pattern: ErrorPattern) -> str:
        """Determine priority level for a pattern."""
        # High priority: frequent errors or critical severity
        if pattern.frequency > 10:
            return 'high'
        
        critical_count = pattern.severity_distribution.get('critical', 0)
        high_count = pattern.severity_distribution.get('high', 0)
        
        if critical_count > 0 or high_count > 5:
            return 'high'
        
        # Medium priority: moderate frequency
        if pattern.frequency > 3:
            return 'medium'
        
        return 'low'
    
    def _generate_recommendation_for_type(
        self,
        pattern: ErrorPattern
    ) -> Optional[ErrorRecommendation]:
        """Generate recommendation for specific error type."""
        error_type = pattern.error_type
        
        recommendations_map = {
            ErrorType.TOOL_FAILURE: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Implement circuit breaker pattern for tool calls",
                rationale=f"Tool failures occurred {pattern.frequency} times. "
                         f"Retry success rate: {pattern.retry_success_rate:.1%}",
                estimated_impact="Reduce tool failure impact by 60-80%"
            ),
            ErrorType.TOKEN_LIMIT: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Implement intelligent context pruning and token budgets",
                rationale=f"Token limit errors occurred {pattern.frequency} times. "
                         "Consider implementing sliding window or summarization.",
                estimated_impact="Eliminate 90%+ of token limit errors"
            ),
            ErrorType.TIMEOUT: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Increase timeout thresholds and implement async processing",
                rationale=f"Timeout errors occurred {pattern.frequency} times. "
                         "Consider async invocation for long-running operations.",
                estimated_impact="Reduce timeout errors by 70-90%"
            ),
            ErrorType.LLM_ERROR: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Implement exponential backoff retry with rate limiting",
                rationale=f"LLM errors occurred {pattern.frequency} times. "
                         f"Current retry success rate: {pattern.retry_success_rate:.1%}",
                estimated_impact="Improve success rate to 95%+ with proper retries"
            ),
            ErrorType.MEMORY_ERROR: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Add fallback to local caching when memory service unavailable",
                rationale=f"Memory errors occurred {pattern.frequency} times. "
                         "Implement graceful degradation with cached responses.",
                estimated_impact="Maintain 80%+ functionality during memory outages"
            ),
            ErrorType.DATABASE_ERROR: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Implement connection pooling and query optimization",
                rationale=f"Database errors occurred {pattern.frequency} times. "
                         "Review query patterns and add connection retry logic.",
                estimated_impact="Reduce database errors by 50-70%"
            ),
            ErrorType.VALIDATION_ERROR: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Add input validation and schema enforcement",
                rationale=f"Validation errors occurred {pattern.frequency} times. "
                         "Implement stricter input validation at API boundary.",
                estimated_impact="Prevent 95%+ of validation errors at entry point"
            ),
            ErrorType.NETWORK_ERROR: ErrorRecommendation(
                error_type=error_type,
                priority=self._determine_priority(pattern),
                recommendation="Implement retry with exponential backoff for network calls",
                rationale=f"Network errors occurred {pattern.frequency} times. "
                         "Add automatic retry for transient network failures.",
                estimated_impact="Resolve 80%+ of transient network errors"
            )
        }
        
        return recommendations_map.get(error_type)
    
    def get_summary_report(self) -> Dict:
        """
        Generate a comprehensive summary report of error patterns.
        
        Returns:
            Dictionary containing error analysis summary
        """
        total_errors = len(self.error_history)
        
        if total_errors == 0:
            return {
                'total_errors': 0,
                'message': 'No errors recorded'
            }
        
        # Get time range
        timestamps = [e.timestamp for e in self.error_history]
        time_range = max(timestamps) - min(timestamps)
        
        # Get frequency by type
        frequency_by_type = self.get_error_frequency()
        
        # Get most common patterns
        common_patterns = self.get_most_common_patterns(top_n=5)
        
        # Get recommendations
        recommendations = self.generate_recommendations()
        
        return {
            'total_errors': total_errors,
            'time_range_hours': time_range.total_seconds() / 3600,
            'error_rate_per_hour': total_errors / max(time_range.total_seconds() / 3600, 1),
            'frequency_by_type': {
                k.value: v for k, v in frequency_by_type.items()
            },
            'most_common_patterns': [p.to_dict() for p in common_patterns],
            'recommendations': [r.to_dict() for r in recommendations],
            'unique_error_types': len(frequency_by_type),
            'affected_scenarios': len(set(
                e.scenario_id for e in self.error_history
                if e.scenario_id is not None
            ))
        }


# Global error pattern detector instance
_pattern_detector: Optional[ErrorPatternDetector] = None


def get_pattern_detector() -> ErrorPatternDetector:
    """
    Get or create the global error pattern detector instance.
    
    Returns:
        ErrorPatternDetector instance
    """
    global _pattern_detector
    if _pattern_detector is None:
        _pattern_detector = ErrorPatternDetector()
    return _pattern_detector
