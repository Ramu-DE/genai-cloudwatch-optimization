"""
Optimization Executors for Wealth Management Agent Performance Testing

Each executor function creates a modified agent context with a specific fault
injected, invokes the Sophia Financial Planner agent (or simulates the
invocation), and returns PerformanceMetrics for comparison against a baseline.
"""

import logging
import time
import os
import json
import uuid
import boto3
from typing import Dict, Any, Optional
from datetime import datetime

from fault_injectors import (
    PerformanceMetrics, AgentContext, estimate_cost,
    generate_raw_transaction_history,
    generate_irrelevant_crm_fields,
    generate_raw_market_feed,
    generate_useless_memory_summary,
    generate_extreme_compliance_history,
)
from scenario_router import ScenarioConfig

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('REGION', 'us-west-2'))
DEFAULT_MODEL = os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0')
SOPHIA_AGENT_ARN = os.environ.get('SOPHIA_AGENT_ARN', '')


# ======================================================================
# Bedrock invocation helper
# ======================================================================

def invoke_bedrock_model(prompt: str, system_prompt: str = "",
                         model_id: str = DEFAULT_MODEL,
                         max_tokens: int = 1024) -> Dict[str, Any]:
    """Invoke a Bedrock model and return response + token metrics."""
    client = boto3.client('bedrock-runtime', region_name=AWS_REGION)

    messages = [{"role": "user", "content": [{"text": prompt}]}]
    system_parts = [{"text": system_prompt}] if system_prompt else []

    start = time.time()
    try:
        resp = client.converse(
            modelId=model_id,
            messages=messages,
            system=system_parts,
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
        )
        latency_ms = (time.time() - start) * 1000
        usage = resp.get('usage', {})
        output_text = ""
        for block in resp.get('output', {}).get('message', {}).get('content', []):
            output_text += block.get('text', '')

        input_tokens = usage.get('inputTokens', 0)
        output_tokens = usage.get('outputTokens', 0)

        return {
            'response': output_text,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'latency_ms': latency_ms,
            'estimated_cost_usd': estimate_cost(input_tokens, output_tokens, model_id),
            'model_id': model_id,
            'error': None,
        }
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.error(f"Bedrock invocation failed: {e}")
        return {
            'response': f"Error: {e}",
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
            'latency_ms': latency_ms,
            'estimated_cost_usd': 0.0,
            'model_id': model_id,
            'error': str(e),
        }


# ======================================================================
# Core execution wrapper
# ======================================================================

def _build_metrics(result: Dict[str, Any], scenario_id: int,
                   extra_latency: float = 0.0, bloat_tokens: int = 0,
                   error_count: int = 0, retry_count: int = 0,
                   tool_calls: int = 1) -> PerformanceMetrics:
    return PerformanceMetrics(
        latency_ms=result['latency_ms'] + extra_latency,
        input_tokens=result['input_tokens'],
        output_tokens=result['output_tokens'],
        total_tokens=result['total_tokens'],
        tool_calls=tool_calls,
        estimated_cost_usd=result['estimated_cost_usd'],
        model_id=result.get('model_id', DEFAULT_MODEL),
        scenario_id=scenario_id,
        injected_latency_ms=extra_latency,
        bloat_tokens=bloat_tokens,
        error_count=error_count,
        retry_count=retry_count,
    )


BASELINE_SYSTEM_PROMPT = (
    "You are Sophia, a certified financial planner at WealthAI Advisors. "
    "Answer concisely using only the information provided."
)


# ======================================================================
# Scenario executors
# ======================================================================

def execute_baseline(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 1/3/5/9 — clean baseline execution."""
    logger.info(f"Executing baseline scenario {scenario.scenario_id}: {scenario.scenario_name}")
    result = invoke_bedrock_model(prompt, BASELINE_SYSTEM_PROMPT)
    metrics = _build_metrics(result, scenario.scenario_id,
                             tool_calls=scenario.expected_impact.get('tool_calls', 1))
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'error' if result['error'] else 'success',
        'response': result['response'],
        'metrics': metrics.to_dict(),
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_context_bloat(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenarios 2, 4, 13 — inject context bloat before the real prompt."""
    logger.info(f"Executing context bloat scenario {scenario.scenario_id}")
    cfg = scenario.fault_config or {}
    bloat_tokens = cfg.get('bloat_tokens', 8000)
    source = cfg.get('bloat_source', 'raw_transaction_history')

    generators = {
        'raw_transaction_history': generate_raw_transaction_history,
        'irrelevant_crm_fields': generate_irrelevant_crm_fields,
        'extreme_compliance_history': generate_extreme_compliance_history,
        'irrelevant_database_fields': generate_irrelevant_crm_fields,
        'extreme_conversation_history': generate_extreme_compliance_history,
    }
    gen = generators.get(source, generate_raw_transaction_history)
    bloat_text = gen(bloat_tokens)

    bloated_prompt = f"{bloat_text}\n\n---\nACTUAL QUESTION: {prompt}"
    result = invoke_bedrock_model(bloated_prompt, BASELINE_SYSTEM_PROMPT)
    metrics = _build_metrics(result, scenario.scenario_id, bloat_tokens=bloat_tokens)
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'error' if result['error'] else 'success',
        'response': result['response'],
        'metrics': metrics.to_dict(),
        'fault_description': f"Injected {bloat_tokens} tokens of {source}",
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_redundant_tools(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 6 — simulate multiple sequential tool calls."""
    logger.info(f"Executing redundant tool calls scenario {scenario.scenario_id}")
    cfg = scenario.fault_config or {}
    redundant = cfg.get('redundant_tools', ['get_client_portfolio', 'assess_portfolio_risk', 'recommend_allocation'])

    total_latency = 0.0
    total_input = 0
    total_output = 0
    total_cost = 0.0
    last_response = ""

    for tool_name in redundant:
        tool_prompt = f"[Tool call: {tool_name}] {prompt}"
        result = invoke_bedrock_model(tool_prompt, BASELINE_SYSTEM_PROMPT, max_tokens=512)
        total_latency += result['latency_ms']
        total_input += result['input_tokens']
        total_output += result['output_tokens']
        total_cost += result['estimated_cost_usd']
        last_response = result['response']

    metrics = PerformanceMetrics(
        latency_ms=total_latency,
        input_tokens=total_input,
        output_tokens=total_output,
        total_tokens=total_input + total_output,
        tool_calls=len(redundant),
        tool_call_breakdown={t: 1 for t in redundant},
        estimated_cost_usd=total_cost,
        model_id=DEFAULT_MODEL,
        scenario_id=scenario.scenario_id,
    )
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'success',
        'response': last_response,
        'metrics': metrics.to_dict(),
        'fault_description': f"Made {len(redundant)} sequential tool calls instead of 1",
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_tool_failure(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 7 — first call fails, second succeeds (retry)."""
    logger.info(f"Executing tool failure scenario {scenario.scenario_id}")
    cfg = scenario.fault_config or {}
    failure_type = cfg.get('failure_type', 'ConnectionTimeout')

    # Simulate failure + wait
    fail_start = time.time()
    time.sleep(1.5)
    fail_latency = (time.time() - fail_start) * 1000

    # Retry succeeds
    result = invoke_bedrock_model(prompt, BASELINE_SYSTEM_PROMPT)
    metrics = _build_metrics(result, scenario.scenario_id,
                             extra_latency=fail_latency,
                             error_count=1, retry_count=1, tool_calls=2)
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'success',
        'response': result['response'],
        'metrics': metrics.to_dict(),
        'fault_description': f"First call raised {failure_type}, retry succeeded",
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_raw_output_bloat(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 8 — tool returns massive unprocessed output."""
    logger.info(f"Executing raw output bloat scenario {scenario.scenario_id}")
    cfg = scenario.fault_config or {}
    raw_tokens = cfg.get('raw_output_tokens', 5000)

    raw_data = generate_raw_market_feed(raw_tokens)
    bloated_prompt = f"Here is the raw market data:\n{raw_data}\n\nBased on this, {prompt}"
    result = invoke_bedrock_model(bloated_prompt, BASELINE_SYSTEM_PROMPT)
    metrics = _build_metrics(result, scenario.scenario_id, bloat_tokens=raw_tokens)
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'error' if result['error'] else 'success',
        'response': result['response'],
        'metrics': metrics.to_dict(),
        'fault_description': f"Tool returned {raw_tokens} tokens of raw OHLCV data",
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_latency_injection(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 10 — simulate slow DynamoDB read."""
    logger.info(f"Executing latency injection scenario {scenario.scenario_id}")
    cfg = scenario.fault_config or {}
    delay = cfg.get('delay_seconds', 4.0)

    time.sleep(delay)
    result = invoke_bedrock_model(prompt, BASELINE_SYSTEM_PROMPT)
    metrics = _build_metrics(result, scenario.scenario_id,
                             extra_latency=delay * 1000)
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'error' if result['error'] else 'success',
        'response': result['response'],
        'metrics': metrics.to_dict(),
        'fault_description': f"Injected {delay}s DynamoDB latency spike",
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_tool_unavailable(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 11 — agent has no tools, must degrade gracefully."""
    logger.info(f"Executing tool unavailable scenario {scenario.scenario_id}")
    no_tools_prompt = (
        f"IMPORTANT: You have NO access to any tools or databases. "
        f"You cannot look up client data. Explain what you would need.\n\n{prompt}"
    )
    result = invoke_bedrock_model(no_tools_prompt, BASELINE_SYSTEM_PROMPT)
    metrics = _build_metrics(result, scenario.scenario_id, tool_calls=0)
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'degraded',
        'response': result['response'],
        'metrics': metrics.to_dict(),
        'fault_description': "All tools removed — testing graceful degradation",
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_memory_misuse(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 12 — inject stale/misleading memory summary."""
    logger.info(f"Executing memory misuse scenario {scenario.scenario_id}")
    bad_summary = generate_useless_memory_summary()
    poisoned_prompt = f"{bad_summary}\nCurrent question: {prompt}"

    result = invoke_bedrock_model(poisoned_prompt, BASELINE_SYSTEM_PROMPT)
    metrics = _build_metrics(result, scenario.scenario_id,
                             bloat_tokens=len(bad_summary) // 4, tool_calls=2)
    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': scenario.scenario_type,
        'status': 'error' if result['error'] else 'success',
        'response': result['response'],
        'metrics': metrics.to_dict(),
        'fault_description': "Injected misleading memory summary contradicting actual data",
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_model_comparison(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 15 — run same prompt across multiple models."""
    logger.info(f"Executing model comparison scenario {scenario.scenario_id}")
    cfg = scenario.optimization_config or {}
    models = cfg.get('models', [
        'us.anthropic.claude-haiku-4-5-20251001-v1:0',
        'us.anthropic.claude-sonnet-4-20250514-v1:0',
    ])

    results_by_model = []
    for model_id in models:
        r = invoke_bedrock_model(prompt, BASELINE_SYSTEM_PROMPT, model_id=model_id)
        results_by_model.append({
            'model_id': model_id,
            'latency_ms': r['latency_ms'],
            'input_tokens': r['input_tokens'],
            'output_tokens': r['output_tokens'],
            'total_tokens': r['total_tokens'],
            'estimated_cost_usd': r['estimated_cost_usd'],
            'response_preview': r['response'][:200],
            'error': r['error'],
        })

    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': 'optimization',
        'status': 'success',
        'model_results': results_by_model,
        'metrics': results_by_model[0] if results_by_model else {},
        'timestamp': datetime.utcnow().isoformat(),
    }


def execute_prompt_compression(scenario: ScenarioConfig, prompt: str) -> Dict[str, Any]:
    """Scenario 16 — compare verbose vs compressed prompts."""
    logger.info(f"Executing prompt compression scenario {scenario.scenario_id}")

    verbose_prompt = (
        f"I would like you to please provide me with a very detailed and comprehensive "
        f"analysis of the following financial topic. Please make sure to include all "
        f"relevant information and supporting details: {prompt}"
    )
    compressed_prompt = f"Concise analysis: {prompt}"

    verbose_result = invoke_bedrock_model(verbose_prompt, BASELINE_SYSTEM_PROMPT)
    compressed_result = invoke_bedrock_model(compressed_prompt, BASELINE_SYSTEM_PROMPT)

    return {
        'execution_id': str(uuid.uuid4())[:8],
        'scenario_id': scenario.scenario_id,
        'scenario_name': scenario.scenario_name,
        'scenario_type': 'optimization',
        'status': 'success',
        'verbose_metrics': {
            'input_tokens': verbose_result['input_tokens'],
            'output_tokens': verbose_result['output_tokens'],
            'total_tokens': verbose_result['total_tokens'],
            'latency_ms': verbose_result['latency_ms'],
            'cost_usd': verbose_result['estimated_cost_usd'],
        },
        'compressed_metrics': {
            'input_tokens': compressed_result['input_tokens'],
            'output_tokens': compressed_result['output_tokens'],
            'total_tokens': compressed_result['total_tokens'],
            'latency_ms': compressed_result['latency_ms'],
            'cost_usd': compressed_result['estimated_cost_usd'],
        },
        'token_savings_percent': round(
            (1 - compressed_result['total_tokens'] / max(verbose_result['total_tokens'], 1)) * 100, 1
        ),
        'metrics': _build_metrics(compressed_result, scenario.scenario_id).to_dict(),
        'timestamp': datetime.utcnow().isoformat(),
    }


# ======================================================================
# Dispatcher
# ======================================================================

EXECUTOR_MAP = {
    'none': execute_baseline,
    'context_bloat': execute_context_bloat,
    'tool_orchestration': execute_redundant_tools,
    'tool_failure': execute_tool_failure,
    'raw_output': execute_raw_output_bloat,
    'latency_injection': execute_latency_injection,
    'tool_unavailable': execute_tool_unavailable,
    'memory_misuse': execute_memory_misuse,
}


def execute_scenario_with_agent(scenario: ScenarioConfig, context) -> Dict[str, Any]:
    """
    Main entry point — dispatches to the correct executor based on
    scenario type and fault_type.
    """
    prompt = getattr(context, 'user_input', '') or scenario.sample_prompt or "Analyze my portfolio"

    # Special optimization scenarios
    if scenario.scenario_id == 15:
        return execute_model_comparison(scenario, prompt)
    if scenario.scenario_id == 16:
        return execute_prompt_compression(scenario, prompt)

    # Standard fault injection / baseline
    executor = EXECUTOR_MAP.get(scenario.fault_type, execute_baseline)
    return executor(scenario, prompt)
