"""
Optimization Executors for Luna Agent Performance Testing

This module provides executors for advanced optimization scenarios including
model comparison, caching strategies, prompt compression, and more.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from fault_injectors import PerformanceMetrics, AgentContext

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result from an optimization scenario execution"""
    scenario_id: int
    scenario_name: str
    strategy_name: str
    metrics: PerformanceMetrics
    quality_score: float = 0.0
    cost_per_quality: float = 0.0
    recommendation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'scenario_id': self.scenario_id,
            'scenario_name': self.scenario_name,
            'strategy_name': self.strategy_name,
            'metrics': self.metrics.to_dict(),
            'quality_score': self.quality_score,
            'cost_per_quality': self.cost_per_quality,
            'recommendation': self.recommendation
        }


class OptimizationExecutor(ABC):
    """Base class for optimization scenario executors"""
    
    def __init__(self, scenario_id: int, scenario_name: str, optimization_config: Optional[Dict[str, Any]] = None):
        self.scenario_id = scenario_id
        self.scenario_name = scenario_name
        self.optimization_config = optimization_config or {}
        logger.info(f"Initialized {self.__class__.__name__} for scenario {scenario_id}")
    
    @abstractmethod
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        """
        Execute optimization scenario and return results for each strategy.
        
        Args:
            context: The agent execution context
            
        Returns:
            List of OptimizationResult for each strategy tested
        """
        pass
    
    def calculate_quality_score(self, response: str, expected_elements: List[str]) -> float:
        """
        Calculate quality score based on response completeness.
        
        Args:
            response: The agent's response
            expected_elements: List of expected elements in response
            
        Returns:
            Quality score between 0.0 and 1.0
        """
        if not expected_elements:
            return 1.0
        
        found_count = sum(1 for element in expected_elements if element.lower() in response.lower())
        return found_count / len(expected_elements)


class ModelComparisonExecutor(OptimizationExecutor):
    """
    Executes model comparison across Claude model family.
    
    Scenario 15: Model Comparison (Haiku vs Sonnet vs Opus)
    Compares cost, latency, and quality across models
    """
    
    def __init__(self, scenario_id: int = 15, scenario_name: str = "Model Comparison", optimization_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, optimization_config)
        self.models = self.optimization_config.get('models', ['claude-3-haiku', 'claude-3-sonnet', 'claude-3-opus'])
        self.compare_metrics = self.optimization_config.get('compare_metrics', ['cost', 'latency', 'quality', 'cost_per_quality'])
    
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        """
        Execute same prompt across multiple models and compare results.
        
        Args:
            context: The agent execution context
            
        Returns:
            List of OptimizationResult for each model
        """
        logger.info(f"Executing model comparison across {len(self.models)} models")
        
        results = []
        
        for model in self.models:
            logger.info(f"Testing model: {model}")
            
            # Simulate model execution with different characteristics
            metrics = self._simulate_model_execution(model, context)
            
            # Calculate quality score (placeholder - would use actual response)
            quality_score = self._estimate_quality_by_model(model)
            
            # Calculate cost per quality
            cost_per_quality = metrics.estimated_cost_usd / quality_score if quality_score > 0 else float('inf')
            
            result = OptimizationResult(
                scenario_id=self.scenario_id,
                scenario_name=self.scenario_name,
                strategy_name=model,
                metrics=metrics,
                quality_score=quality_score,
                cost_per_quality=cost_per_quality
            )
            
            results.append(result)
            logger.info(f"  {model}: ${metrics.estimated_cost_usd:.4f}, {metrics.latency_ms:.0f}ms, quality={quality_score:.2f}")
        
        # Generate recommendation
        best_model = min(results, key=lambda r: r.cost_per_quality)
        best_model.recommendation = f"Best cost-per-quality: {best_model.strategy_name} (${best_model.cost_per_quality:.4f} per quality point)"
        
        logger.info(f"Recommendation: {best_model.recommendation}")
        
        return results
    
    def _simulate_model_execution(self, model: str, context: AgentContext) -> PerformanceMetrics:
        """Simulate model execution with realistic metrics"""
        
        # Model characteristics (approximate)
        model_specs = {
            'claude-3-haiku': {
                'latency_ms': 800,
                'input_cost_per_1k': 0.00025,
                'output_cost_per_1k': 0.00125
            },
            'claude-3-sonnet': {
                'latency_ms': 1500,
                'input_cost_per_1k': 0.003,
                'output_cost_per_1k': 0.015
            },
            'claude-3-opus': {
                'latency_ms': 2500,
                'input_cost_per_1k': 0.015,
                'output_cost_per_1k': 0.075
            }
        }
        
        specs = model_specs.get(model, model_specs['claude-3-sonnet'])
        
        # Estimate tokens
        input_tokens = 300
        output_tokens = 250
        total_tokens = input_tokens + output_tokens
        
        # Calculate cost
        input_cost = (input_tokens / 1000) * specs['input_cost_per_1k']
        output_cost = (output_tokens / 1000) * specs['output_cost_per_1k']
        total_cost = input_cost + output_cost
        
        return PerformanceMetrics(
            latency_ms=specs['latency_ms'],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            tool_calls=1,
            estimated_cost_usd=total_cost,
            scenario_id=self.scenario_id
        )
    
    def _estimate_quality_by_model(self, model: str) -> float:
        """Estimate quality score by model tier"""
        quality_map = {
            'claude-3-haiku': 0.85,
            'claude-3-sonnet': 0.92,
            'claude-3-opus': 0.98
        }
        return quality_map.get(model, 0.90)


class CachingStrategyExecutor(OptimizationExecutor):
    """
    Tests different caching strategies using AgentCore Memory.
    
    Scenario 16: Caching Strategy Comparison
    Tests semantic cache vs exact match cache vs no cache
    """
    
    def __init__(self, scenario_id: int = 16, scenario_name: str = "Caching Strategy Comparison", optimization_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, optimization_config)
        self.strategies = self.optimization_config.get('strategies', ['no_cache', 'semantic_cache', 'exact_match_cache'])
    
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        """Execute caching strategy comparison"""
        logger.info(f"Executing caching strategy comparison")
        
        results = []
        
        for strategy in self.strategies:
            logger.info(f"Testing strategy: {strategy}")
            
            metrics = self._simulate_caching_strategy(strategy, context)
            
            result = OptimizationResult(
                scenario_id=self.scenario_id,
                scenario_name=self.scenario_name,
                strategy_name=strategy,
                metrics=metrics,
                quality_score=1.0,  # Quality same for all caching strategies
                cost_per_quality=metrics.estimated_cost_usd
            )
            
            results.append(result)
            logger.info(f"  {strategy}: {metrics.cache_hits} hits, {metrics.cache_misses} misses")
        
        return results
    
    def _simulate_caching_strategy(self, strategy: str, context: AgentContext) -> PerformanceMetrics:
        """Simulate caching strategy execution"""
        
        if strategy == 'no_cache':
            return PerformanceMetrics(
                latency_ms=1000,
                input_tokens=300,
                output_tokens=250,
                total_tokens=550,
                tool_calls=1,
                estimated_cost_usd=0.006,
                cache_hits=0,
                cache_misses=1,
                scenario_id=self.scenario_id
            )
        elif strategy == 'semantic_cache':
            # 70% hit rate for semantic similarity
            return PerformanceMetrics(
                latency_ms=400,
                input_tokens=100,
                output_tokens=250,
                total_tokens=350,
                tool_calls=0,
                estimated_cost_usd=0.002,
                cache_hits=7,
                cache_misses=3,
                scenario_id=self.scenario_id
            )
        else:  # exact_match_cache
            # 50% hit rate for exact matches
            return PerformanceMetrics(
                latency_ms=300,
                input_tokens=50,
                output_tokens=250,
                total_tokens=300,
                tool_calls=0,
                estimated_cost_usd=0.001,
                cache_hits=5,
                cache_misses=5,
                scenario_id=self.scenario_id
            )


class PromptCompressionExecutor(OptimizationExecutor):
    """
    Tests prompt compression techniques.
    
    Scenario 17: Prompt Compression
    Tests token reduction via compression without quality loss
    """
    
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        """Execute prompt compression comparison"""
        logger.info("Executing prompt compression comparison")
        
        techniques = self.optimization_config.get('techniques', ['remove_redundancy', 'abbreviations', 'structured_format'])
        
        results = []
        baseline_tokens = 500
        
        for technique in techniques:
            logger.info(f"Testing technique: {technique}")
            
            # Simulate compression
            if technique == 'remove_redundancy':
                compressed_tokens = int(baseline_tokens * 0.7)  # 30% reduction
                quality_impact = 0.02  # 2% quality loss
            elif technique == 'abbreviations':
                compressed_tokens = int(baseline_tokens * 0.8)  # 20% reduction
                quality_impact = 0.05  # 5% quality loss
            else:  # structured_format
                compressed_tokens = int(baseline_tokens * 0.75)  # 25% reduction
                quality_impact = 0.01  # 1% quality loss
            
            metrics = PerformanceMetrics(
                latency_ms=1000,
                input_tokens=compressed_tokens,
                output_tokens=200,
                total_tokens=compressed_tokens + 200,
                tool_calls=1,
                estimated_cost_usd=(compressed_tokens + 200) * 0.00001,
                scenario_id=self.scenario_id
            )
            
            quality_score = 1.0 - quality_impact
            
            result = OptimizationResult(
                scenario_id=self.scenario_id,
                scenario_name=self.scenario_name,
                strategy_name=technique,
                metrics=metrics,
                quality_score=quality_score,
                cost_per_quality=metrics.estimated_cost_usd / quality_score,
                recommendation=f"Token reduction: {baseline_tokens - compressed_tokens} ({((baseline_tokens - compressed_tokens) / baseline_tokens * 100):.0f}%)"
            )
            
            results.append(result)
        
        return results


# Placeholder implementations for remaining optimization executors
# These would be fully implemented in a production system

class StreamingVsBatchExecutor(OptimizationExecutor):
    """Scenario 18: Streaming vs Batch Response"""
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        logger.info("StreamingVsBatchExecutor - placeholder implementation")
        return []


class ToolBatchingExecutor(OptimizationExecutor):
    """Scenario 19: Tool Call Batching"""
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        logger.info("ToolBatchingExecutor - placeholder implementation")
        return []


class TokenBudgetEnforcer(OptimizationExecutor):
    """Scenario 20: Token Budget Management"""
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        logger.info("TokenBudgetEnforcer - placeholder implementation")
        return []


class InferenceParameterTuner(OptimizationExecutor):
    """Scenario 21: Inference Parameter Tuning"""
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        logger.info("InferenceParameterTuner - placeholder implementation")
        return []


class ConversationHistoryOptimizer(OptimizationExecutor):
    """Scenario 22: Conversation History Optimization"""
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        logger.info("ConversationHistoryOptimizer - placeholder implementation")
        return []


class GuardrailPerformanceAnalyzer(OptimizationExecutor):
    """Scenario 23: Guardrail Performance Impact"""
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        logger.info("GuardrailPerformanceAnalyzer - placeholder implementation")
        return []


class DynamicModelSelector(OptimizationExecutor):
    """Scenario 31: Dynamic Model Selection"""
    def execute(self, context: AgentContext) -> List[OptimizationResult]:
        logger.info("DynamicModelSelector - placeholder implementation")
        return []



# ============================================================================
# MAIN EXECUTION FUNCTIONS - REAL AGENT INVOCATION
# ============================================================================

import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


def execute_scenario_with_agent(scenario_config, context: AgentContext) -> Dict[str, Any]:
    """
    Execute a single scenario with REAL agent invocation and fault injection.
    
    Args:
        scenario_config: ScenarioConfig object
        context: AgentContext with user input and session info
        
    Returns:
        Dictionary with execution results and real metrics
    """
    from agent_executor import execute_agent_with_scenario
    
    return execute_agent_with_scenario(
        scenario_config,
        context.user_input,
        context.customer_id,
        context.session_id
    )


def execute_parallel_scenarios(fault_config, baseline_config, context: AgentContext, trace_context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Execute fault and baseline scenarios in parallel with REAL agent invocations.
    
    Args:
        fault_config: ScenarioConfig for fault injection
        baseline_config: ScenarioConfig for baseline
        context: AgentContext with user input
        trace_context: X-Ray trace context for propagation (optional)
        
    Returns:
        Dictionary with both results and comparison
    """
    from agent_executor import execute_agent_with_scenario
    
    logger.info(f"Executing parallel scenarios: {fault_config.scenario_id} vs {baseline_config.scenario_id}")
    
    # Log trace context if available
    if trace_context:
        logger.info(f"📍 ===== PARALLEL EXECUTOR X-RAY TRACE =====")
        logger.info(f"📍 Trace ID: {trace_context.get('trace_id', 'N/A')}")
        logger.info(f"📍 Trace Parent: {trace_context.get('trace_parent', 'N/A')}")
        logger.info(f"📍 Propagating to both fault and baseline executions")
        logger.info(f"📍 ==========================================")
    
    execution_id = f"parallel_{int(time.time() * 1000)}"
    
    # Execute both scenarios in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both executions with trace context
        fault_future = executor.submit(
            execute_agent_with_scenario,
            fault_config,
            context.user_input,
            context.customer_id,
            context.session_id,
            trace_context
        )
        baseline_future = executor.submit(
            execute_agent_with_scenario,
            baseline_config,
            context.user_input,
            context.customer_id,
            context.session_id + "_baseline",
            trace_context
        )
        
        # Wait for both to complete
        fault_result = fault_future.result()
        baseline_result = baseline_future.result()
    
    # Calculate comparison metrics
    fault_metrics = fault_result['metrics']
    baseline_metrics = baseline_result['metrics']
    
    latency_delta = fault_metrics['latency_ms'] - baseline_metrics['latency_ms']
    latency_delta_percent = (latency_delta / baseline_metrics['latency_ms'] * 100) if baseline_metrics['latency_ms'] > 0 else 0
    
    token_delta = fault_metrics['total_tokens'] - baseline_metrics['total_tokens']
    token_delta_percent = (token_delta / baseline_metrics['total_tokens'] * 100) if baseline_metrics['total_tokens'] > 0 else 0
    
    cost_delta = fault_metrics['estimated_cost_usd'] - baseline_metrics['estimated_cost_usd']
    tool_call_delta = fault_metrics['tool_calls'] - baseline_metrics['tool_calls']
    
    # Generate root cause analysis
    root_cause = generate_root_cause_analysis(fault_config, fault_metrics, baseline_metrics)
    
    result = {
        'execution_id': execution_id,
        'fault_result': fault_result,
        'baseline_result': baseline_result,
        'comparison': {
            'latency_delta_ms': latency_delta,
            'latency_delta_percent': latency_delta_percent,
            'token_delta': token_delta,
            'token_delta_percent': token_delta_percent,
            'cost_delta_usd': cost_delta,
            'tool_call_delta': tool_call_delta
        },
        'root_cause_analysis': root_cause,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    logger.info(f"Parallel execution completed: Δ{latency_delta:.0f}ms, Δ{token_delta} tokens")
    
    return result


def get_optimization_executor(scenario_config):
    """Get the appropriate optimization executor for a scenario"""
    
    executor_map = {
        15: ModelComparisonExecutor,
        16: CachingStrategyExecutor,
        17: PromptCompressionExecutor,
        18: StreamingVsBatchExecutor,
        19: ToolBatchingExecutor,
        20: TokenBudgetEnforcer,
        21: InferenceParameterTuner,
        22: ConversationHistoryOptimizer,
        23: GuardrailPerformanceAnalyzer,
        31: DynamicModelSelector,
    }
    
    executor_class = executor_map.get(scenario_config.scenario_id)
    
    if not executor_class:
        raise ValueError(f"No executor found for scenario {scenario_config.scenario_id}")
    
    return executor_class(
        scenario_config.scenario_id,
        scenario_config.scenario_name,
        scenario_config.optimization_config
    )


def generate_root_cause_analysis(fault_config, fault_metrics, baseline_metrics) -> str:
    """Generate root cause analysis based on fault type and metrics"""
    
    fault_type = fault_config.fault_type
    latency_increase = fault_metrics['latency_ms'] - baseline_metrics['latency_ms']
    token_increase = fault_metrics['total_tokens'] - baseline_metrics['total_tokens']
    
    # Calculate token percentage safely
    token_percent = (token_increase / baseline_metrics['total_tokens'] * 100) if baseline_metrics['total_tokens'] > 0 else 0
    
    analyses = {
        'latency_injection': f"Latency increased by {latency_increase:.0f}ms due to artificial delays injected into database queries. This simulates slow external service dependencies.",
        
        'context_bloat': f"Token usage increased by {token_increase} tokens ({token_percent:.0f}%) due to excessive context injection. This demonstrates the cost impact of including irrelevant data in prompts.",
        
        'tool_orchestration_fault': f"Performance degraded due to redundant tool calls ({fault_metrics['tool_calls']} vs {baseline_metrics['tool_calls']}). Sequential calls instead of optimized single calls increased latency by {latency_increase:.0f}ms.",
        
        'tool_failure': f"Latency increased by {latency_increase:.0f}ms due to tool failure and retry logic. The agent had to handle errors, analyze them, and retry with corrected parameters.",
        
        'raw_output': f"Token usage increased by {token_increase} tokens due to returning raw, unprocessed tool output. Pre-processing data before returning to the LLM reduces token costs significantly.",
        
        'memory_misuse': f"Performance degraded due to retrieving useless memory summaries. The agent made {fault_metrics['tool_calls']} tool calls vs {baseline_metrics['tool_calls']} baseline, wasting {latency_increase:.0f}ms.",
    }
    
    return analyses.get(fault_type, f"Performance impact: +{latency_increase:.0f}ms latency, +{token_increase} tokens. Fault type: {fault_type}")


import traceback


def execute_single_scenario_with_metrics(scenario_config, context):
    """Execute a single scenario and return metrics"""
    try:
        # Execute the scenario with agent - this already returns all metrics
        result = execute_scenario_with_agent(scenario_config, context)
        
        # The result already has metrics from execute_agent_with_scenario
        # Just return it directly
        return result.get('metrics', result)
        
    except Exception as e:
        logger.error(f"Error executing single scenario: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'error': str(e),
            'latency_ms': 0,
            'cost_usd': 0,
            'estimated_cost_usd': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
            'timestamp': datetime.now().isoformat()
        }

def execute_single_scenario(scenario_config, context):
    """Simple single scenario execution (alias for compatibility)"""
    return execute_single_scenario_with_metrics(scenario_config, context)
