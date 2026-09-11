"""
CloudWatch Custom Metrics Emitter for WealthAI Copilot Agents

Provides:
- Custom CloudWatch metrics (put_metric_data) for per-tool latency, token usage, error rates
- EMF (Embedded Metric Format) structured logging for zero-config CloudWatch dashboards
- X-Ray subsegment annotations for trace filtering
- Cost estimation based on token counts and model pricing

Usage:
    from metrics_emitter import MetricsEmitter
    metrics = MetricsEmitter(agent_name='marcus')

    with metrics.track_tool('get_client_portfolio', client_id='my_client'):
        result = actual_tool_call()

    metrics.emit_agent_response(latency_ms=1250, input_tokens=500, output_tokens=200)
"""

import os
import json
import time
import logging
import boto3
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')
METRICS_NAMESPACE = 'WealthMgmt/Agents'

# Claude model pricing (per 1K tokens, USD)
MODEL_PRICING = {
    'us.anthropic.claude-haiku-4-5-20251001-v1:0': {'input': 0.001, 'output': 0.005},
    'us.anthropic.claude-sonnet-4-20250514-v1:0': {'input': 0.003, 'output': 0.015},
    'us.anthropic.claude-opus-4-20250514-v1:0': {'input': 0.015, 'output': 0.075},
    'default': {'input': 0.001, 'output': 0.005}
}


class MetricsEmitter:
    """Emit CloudWatch custom metrics and EMF logs for agent observability"""

    def __init__(self, agent_name: str, model_id: str = None):
        self.agent_name = agent_name
        self.model_id = model_id or os.environ.get('BEDROCK_MODEL_ID', 'default')
        self._cw_client = None
        self._request_metrics = {
            'tool_calls': 0,
            'tool_errors': 0,
            'memory_hits': 0,
            'memory_misses': 0,
            'total_tool_latency_ms': 0,
        }

    @property
    def cw_client(self):
        if self._cw_client is None:
            try:
                self._cw_client = boto3.client('cloudwatch', region_name=AWS_REGION)
            except Exception as e:
                logger.warning(f"Could not initialize CloudWatch client: {e}")
        return self._cw_client

    @contextmanager
    def track_tool(self, tool_name: str, client_id: str = 'unknown'):
        """Context manager to track tool invocation latency and success/failure"""
        start = time.time()
        error_occurred = False
        try:
            self._request_metrics['tool_calls'] += 1
            yield
        except Exception as e:
            error_occurred = True
            self._request_metrics['tool_errors'] += 1
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            self._request_metrics['total_tool_latency_ms'] += duration_ms

            self._put_metric('ToolLatency', duration_ms, 'Milliseconds', {
                'AgentName': self.agent_name,
                'ToolName': tool_name
            })

            self._put_metric('ToolInvocations', 1, 'Count', {
                'AgentName': self.agent_name,
                'ToolName': tool_name
            })

            if error_occurred:
                self._put_metric('ToolErrors', 1, 'Count', {
                    'AgentName': self.agent_name,
                    'ToolName': tool_name
                })

            self._emit_emf_log({
                'event': 'tool_invocation',
                'agent': self.agent_name,
                'tool': tool_name,
                'client_id': client_id,
                'duration_ms': round(duration_ms, 2),
                'success': not error_occurred,
                '_metrics': {
                    'ToolLatency': duration_ms,
                    'ToolInvocations': 1,
                    'ToolErrors': 1 if error_occurred else 0
                }
            })

            self._add_xray_annotation(tool_name, duration_ms, not error_occurred)

    def track_memory(self, hit: bool, retrieval_ms: float = 0):
        """Track memory retrieval hit/miss rates"""
        if hit:
            self._request_metrics['memory_hits'] += 1
        else:
            self._request_metrics['memory_misses'] += 1

        self._put_metric('MemoryHitRate', 1 if hit else 0, 'Count', {
            'AgentName': self.agent_name,
            'Result': 'Hit' if hit else 'Miss'
        })

        if retrieval_ms > 0:
            self._put_metric('MemoryRetrievalLatency', retrieval_ms, 'Milliseconds', {
                'AgentName': self.agent_name
            })

    def emit_agent_response(self, latency_ms: float, input_tokens: int = 0,
                            output_tokens: int = 0, client_id: str = 'unknown',
                            session_id: str = ''):
        """Emit end-to-end agent response metrics"""
        total_tokens = input_tokens + output_tokens
        cost = self._estimate_cost(input_tokens, output_tokens)

        self._put_metric('AgentResponseTime', latency_ms, 'Milliseconds', {
            'AgentName': self.agent_name
        })

        self._put_metric('InputTokens', input_tokens, 'Count', {
            'AgentName': self.agent_name
        })

        self._put_metric('OutputTokens', output_tokens, 'Count', {
            'AgentName': self.agent_name
        })

        self._put_metric('EstimatedCostUSD', cost, 'None', {
            'AgentName': self.agent_name
        })

        self._put_metric('ToolCallsPerRequest', self._request_metrics['tool_calls'], 'Count', {
            'AgentName': self.agent_name
        })

        total_mem = self._request_metrics['memory_hits'] + self._request_metrics['memory_misses']
        if total_mem > 0:
            hit_rate = (self._request_metrics['memory_hits'] / total_mem) * 100
            self._put_metric('MemoryHitRatePercent', hit_rate, 'Percent', {
                'AgentName': self.agent_name
            })

        self._emit_emf_log({
            'event': 'agent_response',
            'agent': self.agent_name,
            'client_id': client_id,
            'session_id': session_id,
            'latency_ms': round(latency_ms, 2),
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'estimated_cost_usd': round(cost, 6),
            'tool_calls': self._request_metrics['tool_calls'],
            'tool_errors': self._request_metrics['tool_errors'],
            'memory_hits': self._request_metrics['memory_hits'],
            'memory_misses': self._request_metrics['memory_misses'],
            'model_id': self.model_id,
            '_metrics': {
                'AgentResponseTime': latency_ms,
                'InputTokens': input_tokens,
                'OutputTokens': output_tokens,
                'EstimatedCostUSD': cost,
                'ToolCallsPerRequest': self._request_metrics['tool_calls']
            }
        })

        self._reset_request_metrics()

    def emit_dynamodb_latency(self, table_name: str, operation: str, latency_ms: float):
        """Track DynamoDB operation latency"""
        self._put_metric('DynamoDBLatency', latency_ms, 'Milliseconds', {
            'AgentName': self.agent_name,
            'TableName': table_name,
            'Operation': operation
        })

    def emit_compliance_event(self, event_type: str, status: str, client_id: str):
        """Track compliance-specific events (Victor agent)"""
        self._put_metric('ComplianceEvents', 1, 'Count', {
            'EventType': event_type,
            'Status': status
        })

        self._emit_emf_log({
            'event': 'compliance_check',
            'agent': 'victor',
            'event_type': event_type,
            'status': status,
            'client_id': client_id,
            '_metrics': {'ComplianceEvents': 1}
        })

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost based on token counts and model pricing"""
        pricing = MODEL_PRICING.get(self.model_id, MODEL_PRICING['default'])
        input_cost = (input_tokens / 1000) * pricing['input']
        output_cost = (output_tokens / 1000) * pricing['output']
        return input_cost + output_cost

    def _put_metric(self, metric_name: str, value: float, unit: str,
                    dimensions: Dict[str, str] = None):
        """Put a single metric to CloudWatch"""
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow(),
            }
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': v} for k, v in dimensions.items()
                ]

            if self.cw_client:
                self.cw_client.put_metric_data(
                    Namespace=METRICS_NAMESPACE,
                    MetricData=[metric_data]
                )
        except Exception as e:
            logger.debug(f"Could not emit metric {metric_name}: {e}")

    def _emit_emf_log(self, data: Dict[str, Any]):
        """Emit Embedded Metric Format log for CloudWatch automatic metric extraction"""
        metrics_data = data.pop('_metrics', {})

        emf_log = {
            '_aws': {
                'Timestamp': int(time.time() * 1000),
                'CloudWatchMetrics': [{
                    'Namespace': METRICS_NAMESPACE,
                    'Dimensions': [['AgentName']],
                    'Metrics': [
                        {'Name': k, 'Unit': 'None'} for k in metrics_data.keys()
                    ]
                }]
            },
            'AgentName': self.agent_name,
            **data,
            **metrics_data
        }

        print(json.dumps(emf_log))

    def _add_xray_annotation(self, tool_name: str, duration_ms: float, success: bool):
        """Add X-Ray subsegment annotations for trace filtering"""
        try:
            from aws_xray_sdk.core import xray_recorder
            subsegment = xray_recorder.begin_subsegment(f'tool:{tool_name}')
            if subsegment:
                subsegment.put_annotation('agent_name', self.agent_name)
                subsegment.put_annotation('tool_name', tool_name)
                subsegment.put_annotation('success', success)
                subsegment.put_metadata('duration_ms', duration_ms)
                xray_recorder.end_subsegment()
        except Exception:
            pass

    def _reset_request_metrics(self):
        """Reset per-request counters"""
        self._request_metrics = {
            'tool_calls': 0,
            'tool_errors': 0,
            'memory_hits': 0,
            'memory_misses': 0,
            'total_tool_latency_ms': 0,
        }
