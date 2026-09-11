"""
Parallel Execution Orchestrator for Luna Agent Performance Testing

This module orchestrates parallel execution of fault injection and baseline scenarios
with retry logic, graceful degradation, and comprehensive error handling.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from scenario_router import ScenarioRouter, ScenarioConfig
from fault_injectors import (
    FaultInjector, AgentContext, PerformanceMetrics,
    LatencyFaultInjector, ContextBloatInjector, ToolOrchestrationFaultInjector,
    RawToolOutputInjector, MemoryMisuseInjector, OptimalBaselineExecutor
)
from metrics_collector import MetricsCollector, ComparisonResult

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class DualExecutionResult:
    """Result from parallel execution of fault and baseline scenarios"""
    scenario_id: int
    scenario_name: str
    fault_result: Optional[AgentContext] = None
    baseline_result: Optional[AgentContext] = None
    comparison: Optional[ComparisonResult] = None
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = {
            'scenario_id': self.scenario_id,
            'scenario_name': self.scenario_name,
            'execution_time_ms': self.execution_time_ms
        }
        
        if self.fault_result:
            result['fault_metrics'] = self.fault_result.metrics.to_dict()
            result['fault_response'] = self.fault_result.agent_response
        
        if self.baseline_result:
            result['baseline_metrics'] = self.baseline_result.metrics.to_dict()
            result['baseline_response'] = self.baseline_result.agent_response
        
        if self.comparison:
            result['comparison'] = self.comparison.to_dict()
        
        if self.error_message:
            result['error'] = self.error_message
        
        return result


class ParallelExecutionOrchestrator:
    """
    Orchestrates parallel execution of fault injection and baseline scenarios.
    
    Features:
    - Async parallel execution using asyncio.gather()
    - Retry logic with exponential backoff
    - Graceful degradation on failures
    - Comprehensive error handling
    """
    
    def __init__(self):
        """Initialize the orchestrator"""
        self.router = ScenarioRouter()
        self.metrics_collector = MetricsCollector()
        logger.info("ParallelExecutionOrchestrator initialized")
    
    async def execute_parallel_scenarios(self, user_input: str, customer_id: str, 
                                        session_id: str) -> DualExecutionResult:
        """
        Execute fault and baseline scenarios in parallel.
        
        Args:
            user_input: User's input (may contain scenario keyword)
            customer_id: Customer identifier
            session_id: Session identifier
            
        Returns:
            DualExecutionResult with both executions and comparison
        """
        start_time = time.time()
        
        # Parse scenario from user input
        scenario_config = self.router.parse_scenario(user_input)
        
        if scenario_config is None:
            logger.warning("No scenario keyword detected - using default baseline")
            scenario_config = self.router.get_scenario_by_id(1)  # Default to scenario 1
        
        logger.info(f"Executing parallel scenarios for: {scenario_config.scenario_name}")
        
        # Get baseline scenario if this is a fault injection
        baseline_config = None
        if scenario_config.baseline_scenario:
            baseline_config = self.router.get_baseline_scenario(scenario_config.scenario_id)
        
        # Strip scenario keyword from user input
        clean_input = self.router.strip_scenario_keyword(user_input)
        
        try:
            # Execute both scenarios in parallel
            fault_result, baseline_result = await asyncio.gather(
                self._execute_scenario(scenario_config, clean_input, customer_id, session_id),
                self._execute_scenario(baseline_config or scenario_config, clean_input, customer_id, session_id),
                return_exceptions=True
            )
            
            # Handle exceptions from parallel execution
            if isinstance(fault_result, Exception):
                logger.error(f"Fault scenario failed: {fault_result}")
                fault_result = None
            
            if isinstance(baseline_result, Exception):
                logger.error(f"Baseline scenario failed: {baseline_result}")
                baseline_result = None
            
            # Generate comparison if both succeeded
            comparison = None
            if fault_result and baseline_result:
                comparison = self.metrics_collector.compare_executions(
                    scenario_config.scenario_id,
                    scenario_config.scenario_name,
                    fault_result.metrics,
                    baseline_result.metrics
                )
            
            execution_time = (time.time() - start_time) * 1000
            
            return DualExecutionResult(
                scenario_id=scenario_config.scenario_id,
                scenario_name=scenario_config.scenario_name,
                fault_result=fault_result,
                baseline_result=baseline_result,
                comparison=comparison,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            logger.error(f"Parallel execution failed: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            
            return DualExecutionResult(
                scenario_id=scenario_config.scenario_id,
                scenario_name=scenario_config.scenario_name,
                execution_time_ms=execution_time,
                error_message=str(e)
            )
    
    async def _execute_scenario(self, scenario_config: ScenarioConfig, user_input: str,
                               customer_id: str, session_id: str) -> AgentContext:
        """
        Execute a single scenario with retry logic.
        
        Args:
            scenario_config: Scenario configuration
            user_input: User's input
            customer_id: Customer identifier
            session_id: Session identifier
            
        Returns:
            AgentContext with execution results
        """
        logger.info(f"Executing scenario: {scenario_config.scenario_name}")
        
        # Create agent context
        context = self._create_agent_context(user_input, customer_id, session_id, scenario_config)
        
        # Get appropriate fault injector
        injector = self._get_fault_injector(scenario_config)
        
        # Apply fault injection with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Inject fault
                context = injector.inject_fault(context)
                
                # Execute agent (simulated for now)
                context = await self._execute_agent_with_retry(context, max_retries=3)
                
                # Collect metrics
                injector.collect_metrics(context)
                
                logger.info(f"Scenario execution successful: {scenario_config.scenario_name}")
                return context
                
            except Exception as e:
                logger.warning(f"Scenario execution attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    delay = 2 ** attempt
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed - apply graceful degradation
                    logger.error(f"All retry attempts failed for {scenario_config.scenario_name}")
                    context = self._apply_graceful_degradation(context, e)
                    return context
    
    async def _execute_agent_with_retry(self, context: AgentContext, max_retries: int = 3) -> AgentContext:
        """
        Execute agent with exponential backoff retry logic.
        
        Args:
            context: Agent execution context
            max_retries: Maximum number of retry attempts
            
        Returns:
            AgentContext with execution results
        """
        context.start_execution()
        
        for attempt in range(max_retries):
            try:
                # Simulate agent execution
                # In production, this would call the actual Luna agent
                await asyncio.sleep(0.1)  # Simulate processing
                
                # Simulate response
                context.agent_response = f"Simulated response for: {context.user_input}"
                
                # Simulate metrics
                context.metrics.input_tokens = 300
                context.metrics.output_tokens = 250
                context.metrics.total_tokens = 550
                context.metrics.tool_calls = 1
                context.metrics.estimated_cost_usd = 0.006
                
                context.end_execution()
                
                logger.debug(f"Agent execution successful on attempt {attempt + 1}")
                return context
                
            except Exception as e:
                logger.warning(f"Agent execution attempt {attempt + 1} failed: {e}")
                context.metrics.retry_count += 1
                
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = 2 ** attempt
                    logger.info(f"Retrying agent execution in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    # All retries failed
                    logger.error("All agent execution retries failed")
                    context.error_message = f"Agent execution failed after {max_retries} attempts: {str(e)}"
                    context.metrics.error_count += 1
                    context.end_execution()
                    raise
    
    def _create_agent_context(self, user_input: str, customer_id: str, session_id: str,
                             scenario_config: ScenarioConfig) -> AgentContext:
        """Create agent execution context"""
        metrics = PerformanceMetrics(
            latency_ms=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            tool_calls=0,
            scenario_id=scenario_config.scenario_id
        )
        
        return AgentContext(
            user_input=user_input,
            customer_id=customer_id,
            session_id=session_id,
            system_prompt="You are Luna, a nutrition assistant.",
            tools=["get_user_data", "get_nutrition_plan", "get_recent_meals"],
            metrics=metrics,
            scenario_config=scenario_config
        )
    
    def _get_fault_injector(self, scenario_config: ScenarioConfig) -> FaultInjector:
        """Get appropriate fault injector for scenario"""
        scenario_id = scenario_config.scenario_id
        fault_type = scenario_config.fault_type
        
        # Map scenarios to injectors
        if scenario_id == 10:
            return LatencyFaultInjector(scenario_id, scenario_config.scenario_name, scenario_config.fault_config)
        elif scenario_id in [2, 4, 13]:
            return ContextBloatInjector(scenario_id, scenario_config.scenario_name, scenario_config.fault_config)
        elif scenario_id in [6, 7, 11]:
            return ToolOrchestrationFaultInjector(scenario_id, scenario_config.scenario_name, scenario_config.fault_config)
        elif scenario_id == 8:
            return RawToolOutputInjector(scenario_id, scenario_config.scenario_name, scenario_config.fault_config)
        elif scenario_id == 12:
            return MemoryMisuseInjector(scenario_id, scenario_config.scenario_name, scenario_config.fault_config)
        elif scenario_id in [1, 3, 5, 9]:
            return OptimalBaselineExecutor(scenario_id, scenario_config.scenario_name, scenario_config.fault_config)
        else:
            # Default to optimal baseline
            return OptimalBaselineExecutor(scenario_id, scenario_config.scenario_name, scenario_config.fault_config)
    
    def _apply_graceful_degradation(self, context: AgentContext, error: Exception) -> AgentContext:
        """
        Apply graceful degradation when execution fails.
        
        Strategies:
        - Return cached response if available
        - Return simplified response
        - Return error message with alternatives
        
        Args:
            context: Agent execution context
            error: The exception that occurred
            
        Returns:
            AgentContext with degraded response
        """
        logger.info("Applying graceful degradation")
        
        # Strategy 1: Check for cached response (placeholder)
        cached_response = self._get_cached_response(context.user_input)
        if cached_response:
            logger.info("Using cached response")
            context.agent_response = f"[CACHED] {cached_response}"
            context.metrics.cache_hits = 1
            return context
        
        # Strategy 2: Provide simplified response
        logger.info("Providing simplified response")
        context.agent_response = (
            f"I apologize, but I'm experiencing technical difficulties. "
            f"For nutrition advice, please try: "
            f"1) Consulting our knowledge base at /help "
            f"2) Contacting support at support@example.com "
            f"3) Trying again in a few moments"
        )
        context.error_message = f"Degraded response due to: {str(error)}"
        
        return context
    
    def _get_cached_response(self, user_input: str) -> Optional[str]:
        """
        Get cached response for user input.
        
        In production, this would query AgentCore Memory or a cache service.
        
        Args:
            user_input: User's input
            
        Returns:
            Cached response if available, None otherwise
        """
        # Placeholder - would implement actual caching logic
        return None


# Global orchestrator instance
orchestrator = ParallelExecutionOrchestrator()
