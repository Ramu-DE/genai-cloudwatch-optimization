#!/usr/bin/env python3
"""
Lambda Handler for Wealth Management Agent Optimization System

Handles HTTP API Gateway requests for performance testing and
optimization scenarios against the Sophia Financial Planner agent.
"""

import json
import logging
import traceback
import time
import os
from datetime import datetime

from scenario_router import ScenarioRouter
from metrics_collector import ComparisonResult, emit_scenario_metrics_log, compare_all_scenarios

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ======================================================================
# Lambda entry point
# ======================================================================

def lambda_handler(event, context):
    """
    Supported routes:
      POST /optimize          — execute single scenario (fault or baseline)
      POST /parallel          — run fault + baseline side-by-side, return comparison
      GET  /scenarios         — list available scenarios
      GET  /health            — health check
    """
    logger.info(json.dumps({'event_path': event.get('requestContext', {}).get('http', {}).get('path'),
                            'method': event.get('requestContext', {}).get('http', {}).get('method')}))

    # --- X-Ray trace propagation ---
    headers = event.get('headers', {}) or {}
    trace_header = headers.get('X-Amzn-Trace-Id') or headers.get('x-amzn-trace-id') or ''
    trace_id, trace_parent = '', ''
    for part in trace_header.split(';'):
        if part.startswith('Root='):
            trace_id = part.split('=', 1)[1]
        elif part.startswith('Parent='):
            trace_parent = part.split('=', 1)[1]

    trace_context = {'trace_header': trace_header, 'trace_id': trace_id, 'trace_parent': trace_parent}

    try:
        http_method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        path = event.get('requestContext', {}).get('http', {}).get('path', '/')
        raw_body = event.get('body', '{}')
        body_data = json.loads(raw_body) if isinstance(raw_body, str) and raw_body else {}

        # Routing
        if path in ('/health', '/prod/health'):
            return handle_health()

        if path in ('/scenarios', '/prod/scenarios'):
            return handle_list_scenarios()

        if path in ('/optimize', '/prod/optimize', '/execute-scenario', '/prod/execute-scenario'):
            if http_method == 'POST':
                return handle_optimize(body_data, trace_context)
            return _error(405, "Method not allowed")

        if path in ('/parallel', '/prod/parallel'):
            if http_method == 'POST':
                return handle_parallel(body_data, trace_context)
            return _error(405, "Method not allowed")

        if path in ('/batch', '/prod/batch'):
            if http_method == 'POST':
                return handle_batch(body_data, trace_context)
            return _error(405, "Method not allowed")

        return _error(404, f"Route not found: {path}")

    except Exception as exc:
        logger.error(f"Unhandled: {exc}")
        logger.error(traceback.format_exc())
        return _error(500, str(exc))


# ======================================================================
# Route handlers
# ======================================================================

def handle_health():
    return _ok({
        'status': 'healthy',
        'service': 'wealth-mgmt-optimization',
        'timestamp': datetime.utcnow().isoformat(),
    })


def handle_list_scenarios():
    router = ScenarioRouter()
    return _ok({'scenarios': router.list_scenarios(), 'total': len(router.scenarios)})


def handle_optimize(body: dict, trace_ctx: dict):
    """Execute a single scenario (fault injection or baseline)."""
    scenario_id = body.get('scenario_id')
    prompt = body.get('prompt', '')
    client_id = body.get('client_id', 'client_sarah_chen')

    if scenario_id is None:
        return _error(400, "Missing required field: scenario_id")

    router = ScenarioRouter()
    scenario = router.get_scenario_by_id(int(scenario_id))
    if not scenario:
        return _error(404, f"Scenario {scenario_id} not found")

    from optimization_executors import execute_scenario_with_agent

    class Ctx:
        def __init__(self, ui, cid):
            self.user_input = ui
            self.client_id = cid
            self.session_id = f"opt_{datetime.utcnow().timestamp()}"

    result = execute_scenario_with_agent(scenario, Ctx(prompt or scenario.sample_prompt or "Analyze my portfolio", client_id))

    # Flatten metrics to top-level for frontend compat
    metrics = result.get('metrics', {})
    if isinstance(metrics, dict):
        result['latency_ms'] = metrics.get('latency_ms', 0)
        result['estimated_cost_usd'] = metrics.get('estimated_cost_usd', 0)
        result['total_tokens'] = metrics.get('total_tokens', 0)
        result['input_tokens'] = metrics.get('input_tokens', 0)
        result['output_tokens'] = metrics.get('output_tokens', 0)
        result['tool_calls'] = metrics.get('tool_calls', 0)

    result['trace_id'] = trace_ctx.get('trace_id', '')
    return _ok(result)


def handle_parallel(body: dict, trace_ctx: dict):
    """
    Run fault scenario + its baseline in parallel,
    return side-by-side comparison with deltas and root cause.
    """
    scenario_id = body.get('scenario_id')
    prompt = body.get('prompt', '')
    client_id = body.get('client_id', 'client_sarah_chen')

    if scenario_id is None:
        return _error(400, "Missing required field: scenario_id")

    router = ScenarioRouter()
    fault_scenario = router.get_scenario_by_id(int(scenario_id))
    if not fault_scenario:
        return _error(404, f"Scenario {scenario_id} not found")

    baseline_scenario = router.get_baseline_for(int(scenario_id))
    if not baseline_scenario:
        baseline_scenario = router.get_scenario_by_id(1)

    from optimization_executors import execute_scenario_with_agent
    from fault_injectors import PerformanceMetrics

    class Ctx:
        def __init__(self, ui, cid):
            self.user_input = ui
            self.client_id = cid
            self.session_id = f"par_{datetime.utcnow().timestamp()}"

    ctx = Ctx(prompt or fault_scenario.sample_prompt or "Analyze my portfolio", client_id)

    # Execute both
    fault_result = execute_scenario_with_agent(fault_scenario, ctx)
    baseline_result = execute_scenario_with_agent(baseline_scenario, ctx)

    # Build PerformanceMetrics from result dicts
    def _to_pm(r, sid):
        m = r.get('metrics', {})
        if isinstance(m, PerformanceMetrics):
            return m
        return PerformanceMetrics(
            latency_ms=m.get('latency_ms', 0),
            input_tokens=m.get('input_tokens', 0),
            output_tokens=m.get('output_tokens', 0),
            total_tokens=m.get('total_tokens', 0),
            tool_calls=m.get('tool_calls', 0),
            estimated_cost_usd=m.get('estimated_cost_usd', 0),
            scenario_id=sid,
            injected_latency_ms=m.get('injected_latency_ms', 0),
            bloat_tokens=m.get('bloat_tokens', 0),
            error_count=m.get('error_count', 0),
            retry_count=m.get('retry_count', 0),
        )

    comparison = ComparisonResult(
        scenario_id=fault_scenario.scenario_id,
        scenario_name=fault_scenario.scenario_name,
        fault_metrics=_to_pm(fault_result, fault_scenario.scenario_id),
        baseline_metrics=_to_pm(baseline_result, baseline_scenario.scenario_id),
    )

    emit_scenario_metrics_log(comparison)

    return _ok({
        'comparison': comparison.to_dict(),
        'fault': fault_result,
        'baseline': baseline_result,
        'trace_id': trace_ctx.get('trace_id', ''),
    })


def handle_batch(body: dict, trace_ctx: dict):
    """Run multiple scenarios and return aggregate summary."""
    scenario_ids = body.get('scenario_ids', list(range(1, 17)))
    prompt = body.get('prompt', 'Analyze my portfolio')
    client_id = body.get('client_id', 'client_sarah_chen')

    router = ScenarioRouter()
    from optimization_executors import execute_scenario_with_agent
    from fault_injectors import PerformanceMetrics

    class Ctx:
        def __init__(self, ui, cid):
            self.user_input = ui
            self.client_id = cid
            self.session_id = f"batch_{datetime.utcnow().timestamp()}"

    ctx = Ctx(prompt, client_id)
    comparisons = []

    for sid in scenario_ids:
        scenario = router.get_scenario_by_id(int(sid))
        if not scenario:
            continue
        baseline = router.get_baseline_for(int(sid)) or router.get_scenario_by_id(1)

        fault_result = execute_scenario_with_agent(scenario, ctx)
        baseline_result = execute_scenario_with_agent(baseline, ctx)

        def _to_pm(r, _sid):
            m = r.get('metrics', {})
            return PerformanceMetrics(
                latency_ms=m.get('latency_ms', 0),
                input_tokens=m.get('input_tokens', 0),
                output_tokens=m.get('output_tokens', 0),
                total_tokens=m.get('total_tokens', 0),
                tool_calls=m.get('tool_calls', 0),
                estimated_cost_usd=m.get('estimated_cost_usd', 0),
                scenario_id=_sid,
                injected_latency_ms=m.get('injected_latency_ms', 0),
                bloat_tokens=m.get('bloat_tokens', 0),
                error_count=m.get('error_count', 0),
                retry_count=m.get('retry_count', 0),
            )

        comp = ComparisonResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.scenario_name,
            fault_metrics=_to_pm(fault_result, scenario.scenario_id),
            baseline_metrics=_to_pm(baseline_result, baseline.scenario_id),
        )
        emit_scenario_metrics_log(comp)
        comparisons.append(comp)

    summary = compare_all_scenarios(comparisons)
    summary['trace_id'] = trace_ctx.get('trace_id', '')
    return _ok(summary)


# ======================================================================
# Response helpers
# ======================================================================

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Content-Type': 'application/json',
}


def _ok(data: dict, status: int = 200) -> dict:
    return {'statusCode': status, 'headers': CORS_HEADERS, 'body': json.dumps(data, default=str)}


def _error(status: int, message: str) -> dict:
    return {'statusCode': status, 'headers': CORS_HEADERS, 'body': json.dumps({'error': message})}
