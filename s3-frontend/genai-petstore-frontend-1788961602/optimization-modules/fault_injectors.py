"""
Fault Injectors for Luna Agent Performance Testing

This module provides the base FaultInjector abstract class and common
infrastructure for implementing fault injection scenarios.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics collected during agent execution"""
    latency_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_calls: int
    tool_call_breakdown: Dict[str, int] = field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    scenario_id: Optional[int] = None
    
    # Additional metrics for fault injection analysis
    injected_latency_ms: float = 0.0
    bloat_tokens: int = 0
    error_count: int = 0
    retry_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization"""
        return {
            'latency_ms': self.latency_ms,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'tool_calls': self.tool_calls,
            'tool_call_breakdown': self.tool_call_breakdown,
            'estimated_cost_usd': self.estimated_cost_usd,
            'timestamp': self.timestamp.isoformat(),
            'scenario_id': self.scenario_id,
            'injected_latency_ms': self.injected_latency_ms,
            'bloat_tokens': self.bloat_tokens,
            'error_count': self.error_count,
            'retry_count': self.retry_count,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses
        }


@dataclass
class AgentContext:
    """Context for agent execution with fault injection capabilities"""
    user_input: str
    customer_id: str
    session_id: str
    system_prompt: str
    tools: List[Any]
    metrics: PerformanceMetrics
    scenario_config: Optional[Any] = None
    
    # Execution state
    execution_start_time: Optional[float] = None
    execution_end_time: Optional[float] = None
    
    # Fault injection state
    fault_injected: bool = False
    fault_description: str = ""
    
    # Response data
    agent_response: str = ""
    error_message: Optional[str] = None
    
    def start_execution(self):
        """Mark the start of execution"""
        self.execution_start_time = time.time()
        logger.debug(f"Execution started for session {self.session_id}")
    
    def end_execution(self):
        """Mark the end of execution and calculate latency"""
        self.execution_end_time = time.time()
        if self.execution_start_time:
            latency_seconds = self.execution_end_time - self.execution_start_time
            self.metrics.latency_ms = latency_seconds * 1000
            logger.debug(f"Execution completed in {self.metrics.latency_ms:.2f}ms")
    
    def add_metric(self, key: str, value: Any):
        """Add a custom metric to the context"""
        if hasattr(self.metrics, key):
            setattr(self.metrics, key, value)
        else:
            logger.warning(f"Attempted to set unknown metric: {key}")


class FaultInjectionError(Exception):
    """Base exception for fault injection failures"""
    pass


class ScenarioNotFoundError(FaultInjectionError):
    """Raised when scenario ID is invalid"""
    pass


class MetricsCollectionError(FaultInjectionError):
    """Raised when metrics cannot be collected"""
    pass


class FaultInjector(ABC):
    """
    Abstract base class for fault injection implementations.
    
    Each concrete fault injector implements specific anti-patterns or
    performance degradation scenarios for testing and analysis.
    """
    
    def __init__(self, scenario_id: int, scenario_name: str, fault_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the fault injector.
        
        Args:
            scenario_id: Unique identifier for the scenario
            scenario_name: Human-readable name for the scenario
            fault_config: Configuration parameters for the fault injection
        """
        self.scenario_id = scenario_id
        self.scenario_name = scenario_name
        self.fault_config = fault_config or {}
        
        logger.info(f"Initialized {self.__class__.__name__} for scenario {scenario_id}: {scenario_name}")
    
    @abstractmethod
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        Inject fault into agent execution context.
        
        This method modifies the agent context to introduce the specific
        fault or anti-pattern being tested.
        
        Args:
            context: The agent execution context
            
        Returns:
            Modified agent context with fault injected
            
        Raises:
            FaultInjectionError: If fault injection fails
        """
        pass
    
    @abstractmethod
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Calculate theoretical optimal performance metrics.
        
        Returns the expected metrics for the optimized baseline scenario
        that this fault injection is compared against.
        
        Returns:
            PerformanceMetrics representing the optimal baseline
        """
        pass
    
    def log_fault_injection(self, context: AgentContext, fault_description: str):
        """
        Log fault injection details for observability.
        
        Args:
            context: The agent execution context
            fault_description: Description of the injected fault
        """
        context.fault_injected = True
        context.fault_description = fault_description
        
        logger.info(f"Fault injected for scenario {self.scenario_id}: {self.scenario_name}")
        logger.info(f"  Description: {fault_description}")
        logger.info(f"  Session: {context.session_id}")
        logger.info(f"  Customer: {context.customer_id}")
    
    def collect_metrics(self, context: AgentContext) -> PerformanceMetrics:
        """
        Collect performance metrics from the execution context.
        
        This method provides common metrics collection logic that can be
        extended by concrete implementations.
        
        Args:
            context: The agent execution context
            
        Returns:
            PerformanceMetrics collected from the execution
        """
        metrics = context.metrics
        metrics.scenario_id = self.scenario_id
        
        logger.debug(f"Collected metrics for scenario {self.scenario_id}:")
        logger.debug(f"  Latency: {metrics.latency_ms:.2f}ms")
        logger.debug(f"  Total tokens: {metrics.total_tokens}")
        logger.debug(f"  Tool calls: {metrics.tool_calls}")
        logger.debug(f"  Estimated cost: ${metrics.estimated_cost_usd:.4f}")
        
        return metrics
    
    def handle_error(self, context: AgentContext, error: Exception):
        """
        Handle errors during fault injection.
        
        Args:
            context: The agent execution context
            error: The exception that occurred
        """
        error_msg = f"Error in {self.__class__.__name__}: {str(error)}"
        logger.error(error_msg, exc_info=True)
        
        context.error_message = error_msg
        context.metrics.error_count += 1
        
        # Emit CloudWatch metric for error tracking
        self._emit_error_metric(error)
    
    def _emit_error_metric(self, error: Exception):
        """
        Emit CloudWatch metric for error tracking.
        
        This is a placeholder for future CloudWatch integration.
        
        Args:
            error: The exception that occurred
        """
        # TODO: Implement CloudWatch metrics emission in task 5
        logger.debug(f"Would emit CloudWatch metric for error: {type(error).__name__}")
    
    def validate_context(self, context: AgentContext):
        """
        Validate that the agent context has required fields.
        
        Args:
            context: The agent execution context
            
        Raises:
            FaultInjectionError: If context is invalid
        """
        required_fields = ['user_input', 'customer_id', 'session_id', 'system_prompt', 'tools', 'metrics']
        
        for field in required_fields:
            if not hasattr(context, field):
                raise FaultInjectionError(f"AgentContext missing required field: {field}")
            
            value = getattr(context, field)
            if value is None:
                raise FaultInjectionError(f"AgentContext field is None: {field}")
        
        logger.debug("AgentContext validation passed")


class NoOpFaultInjector(FaultInjector):
    """
    No-operation fault injector for baseline scenarios.
    
    This injector does not modify the agent context and represents
    the optimal execution path without any faults.
    """
    
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        No fault injection - returns context unchanged.
        
        Args:
            context: The agent execution context
            
        Returns:
            Unmodified agent context
        """
        logger.info(f"NoOp injector for baseline scenario {self.scenario_id}: {self.scenario_name}")
        return context
    
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Return theoretical optimal metrics.
        
        Returns:
            PerformanceMetrics with optimal values
        """
        return PerformanceMetrics(
            latency_ms=1000.0,  # 1 second baseline
            input_tokens=250,
            output_tokens=200,
            total_tokens=450,
            tool_calls=1,
            estimated_cost_usd=0.005,
            scenario_id=self.scenario_id
        )


# ============================================================================
# Concrete Fault Injector Implementations
# ============================================================================


class LatencyFaultInjector(FaultInjector):
    """
    Injects artificial latency to simulate slow external service calls.
    
    Scenario 10: DynamoDB Latency Spike
    Demonstrates real-world impact of slow external service (4s delay)
    """
    
    def __init__(self, scenario_id: int = 10, scenario_name: str = "DynamoDB Latency Spike", fault_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, fault_config)
        self.delay_seconds = self.fault_config.get('delay_seconds', 4.0)
        self.delay_location = self.fault_config.get('delay_location', 'database_query')
    
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        Inject latency delay into agent execution.
        
        Args:
            context: The agent execution context
            
        Returns:
            Modified agent context with latency injected
        """
        self.validate_context(context)
        
        fault_description = f"Injecting {self.delay_seconds}s latency to simulate slow {self.delay_location}"
        self.log_fault_injection(context, fault_description)
        
        # Record start time
        start_time = time.time()
        
        # Inject the delay
        logger.info(f"Sleeping for {self.delay_seconds} seconds to simulate latency...")
        time.sleep(self.delay_seconds)
        
        # Calculate actual injected latency
        actual_delay = (time.time() - start_time) * 1000  # Convert to ms
        context.metrics.injected_latency_ms = actual_delay
        
        logger.info(f"Latency injection complete: {actual_delay:.2f}ms")
        
        # Emit CloudWatch metric (placeholder)
        self._emit_latency_metric(actual_delay)
        
        return context
    
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Return baseline metrics without latency injection.
        
        Returns:
            PerformanceMetrics for optimal execution
        """
        return PerformanceMetrics(
            latency_ms=1000.0,  # 1 second baseline
            input_tokens=250,
            output_tokens=200,
            total_tokens=450,
            tool_calls=1,
            estimated_cost_usd=0.005,
            scenario_id=1  # Baseline scenario 1
        )
    
    def _emit_latency_metric(self, latency_ms: float):
        """
        Emit CloudWatch metric for latency spike.
        
        This is a placeholder for future CloudWatch integration.
        
        Args:
            latency_ms: The injected latency in milliseconds
        """
        # TODO: Implement CloudWatch metrics emission in task 5
        logger.debug(f"Would emit CloudWatch metric: InjectedLatency={latency_ms}ms")


class ContextBloatInjector(FaultInjector):
    """
    Injects bloated context to simulate inefficient prompt engineering.
    
    Scenarios:
    - Scenario 2: Context Bloat (Raw RAG) - 8000 tokens from raw conversation history
    - Scenario 4: Irrelevant Context Bloat - 8000 tokens from irrelevant database fields
    - Scenario 13: Maximum Token Limit Breach - 15000 tokens extreme context
    """
    
    def __init__(self, scenario_id: int, scenario_name: str, fault_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, fault_config)
        self.bloat_tokens = self.fault_config.get('bloat_tokens', 8000)
        self.bloat_source = self.fault_config.get('bloat_source', 'raw_conversation_history')
    
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        Inject bloated context into system prompt.
        
        Args:
            context: The agent execution context
            
        Returns:
            Modified agent context with bloated prompt
        """
        self.validate_context(context)
        
        # Generate bloat text based on source type
        bloat_text = self._generate_bloat_text(self.bloat_tokens, self.bloat_source)
        
        fault_description = f"Injecting {self.bloat_tokens} tokens of {self.bloat_source} into system prompt"
        self.log_fault_injection(context, fault_description)
        
        # Inject bloat into system prompt
        context.system_prompt = f"{context.system_prompt}\n\n{bloat_text}"
        context.metrics.bloat_tokens = self.bloat_tokens
        
        logger.info(f"Context bloat injected: {self.bloat_tokens} tokens from {self.bloat_source}")
        
        return context
    
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Return baseline metrics without context bloat.
        
        Returns:
            PerformanceMetrics for optimal execution
        """
        # Baseline depends on scenario type
        if self.scenario_id == 2:
            baseline_id = 3  # Optimal RAG Summary
        elif self.scenario_id in [4, 13]:
            baseline_id = 1  # Optimized Base Case
        else:
            baseline_id = 1
        
        return PerformanceMetrics(
            latency_ms=1000.0,
            input_tokens=250,
            output_tokens=200,
            total_tokens=450,
            tool_calls=1,
            estimated_cost_usd=0.005,
            scenario_id=baseline_id
        )
    
    def _generate_bloat_text(self, token_count: int, source_type: str) -> str:
        """
        Generate bloat text to simulate inefficient context.
        
        Args:
            token_count: Approximate number of tokens to generate
            source_type: Type of bloat source
            
        Returns:
            Generated bloat text
        """
        # Approximate 4 characters per token
        char_count = token_count * 4
        
        if source_type == 'raw_conversation_history':
            bloat = self._generate_raw_conversation_bloat(char_count)
        elif source_type == 'irrelevant_database_fields':
            bloat = self._generate_database_bloat(char_count)
        elif source_type == 'extreme_conversation_history':
            bloat = self._generate_extreme_bloat(char_count)
        else:
            bloat = self._generate_generic_bloat(char_count)
        
        return bloat
    
    def _generate_raw_conversation_bloat(self, char_count: int) -> str:
        """Generate bloat simulating raw conversation history"""
        bloat = "## RAW CONVERSATION HISTORY (UNPROCESSED)\n\n"
        
        sample_turns = [
            "User: Hi, I'm looking for nutrition advice.\nAssistant: Hello! I'd be happy to help with nutrition advice. What specific questions do you have?",
            "User: What should I eat for breakfast?\nAssistant: For a healthy breakfast, I recommend options like oatmeal with fruits, Greek yogurt with nuts, or whole grain toast with avocado and eggs.",
            "User: How many calories should I eat?\nAssistant: Calorie needs vary based on age, gender, activity level, and goals. Generally, adults need 1800-2500 calories per day.",
            "User: Tell me about protein.\nAssistant: Protein is essential for muscle repair and growth. Good sources include lean meats, fish, eggs, legumes, and dairy products.",
            "User: What about carbohydrates?\nAssistant: Carbohydrates are your body's primary energy source. Focus on complex carbs like whole grains, vegetables, and fruits.",
        ]
        
        bloat_content = ""
        while len(bloat_content) < char_count:
            for turn in sample_turns:
                bloat_content += f"{turn}\n\n"
                if len(bloat_content) >= char_count:
                    break
        
        return bloat + bloat_content[:char_count]
    
    def _generate_database_bloat(self, char_count: int) -> str:
        """Generate bloat simulating irrelevant database fields"""
        bloat = "## COMPLETE DATABASE DUMP (ALL FIELDS)\n\n"
        
        irrelevant_fields = [
            "internal_id: 847392847392847\n",
            "created_timestamp: 2023-01-15T08:23:45.123Z\n",
            "modified_timestamp: 2023-11-08T14:32:11.456Z\n",
            "database_version: 3.2.1\n",
            "schema_migration_id: migration_20231015_v2\n",
            "audit_log_reference: audit_log_847392\n",
            "backup_status: completed\n",
            "replication_lag_ms: 45\n",
            "partition_key: partition_us_east_1_shard_3\n",
            "sort_key: sort_2023_11_08\n",
            "ttl_expiration: 1735689600\n",
            "encryption_key_id: key_arn_aws_kms_us_east_1\n",
            "access_control_list: [admin, read_only, analytics]\n",
            "data_classification: internal_use_only\n",
            "compliance_tags: [hipaa, gdpr, ccpa]\n",
        ]
        
        bloat_content = ""
        while len(bloat_content) < char_count:
            for field in irrelevant_fields:
                bloat_content += field
                if len(bloat_content) >= char_count:
                    break
        
        return bloat + bloat_content[:char_count]
    
    def _generate_extreme_bloat(self, char_count: int) -> str:
        """Generate extreme bloat for token limit testing"""
        bloat = "## EXTREME CONTEXT VOLUME (TESTING TOKEN LIMITS)\n\n"
        
        # Generate repetitive content to reach extreme token counts
        filler = "This is filler content to test maximum token limits. " * 100
        
        bloat_content = ""
        while len(bloat_content) < char_count:
            bloat_content += filler
        
        return bloat + bloat_content[:char_count]
    
    def _generate_generic_bloat(self, char_count: int) -> str:
        """Generate generic bloat text"""
        bloat = "## ADDITIONAL CONTEXT\n\n"
        filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50
        
        bloat_content = ""
        while len(bloat_content) < char_count:
            bloat_content += filler
        
        return bloat + bloat_content[:char_count]


class ToolOrchestrationFaultInjector(FaultInjector):
    """
    Injects tool orchestration faults to simulate poor tool usage patterns.
    
    Scenarios:
    - Scenario 6: Redundant Tool Calls - Multiple calls that could be bundled
    - Scenario 7: Tool Failure and Self-Correction - Simulated tool failures
    - Scenario 11: Agent Refusal - Tool Unavailability - All tools removed
    """
    
    def __init__(self, scenario_id: int, scenario_name: str, fault_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, fault_config)
        self.redundant_tools = self.fault_config.get('redundant_tools', [])
        self.failing_tool = self.fault_config.get('failing_tool')
        self.failure_type = self.fault_config.get('failure_type', 'ValueError')
        self.retry_count = self.fault_config.get('retry_count', 1)
        self.remove_all_tools = self.fault_config.get('remove_all_tools', False)
    
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        Inject tool orchestration fault.
        
        Args:
            context: The agent execution context
            
        Returns:
            Modified agent context with tool fault injected
        """
        self.validate_context(context)
        
        if self.remove_all_tools:
            # Scenario 11: Remove all tools
            fault_description = "Removing all tools to simulate unavailability"
            self.log_fault_injection(context, fault_description)
            context.tools = []
            logger.info("All tools removed - agent will be unable to access data")
            
        elif self.failing_tool:
            # Scenario 7: Inject tool failure
            fault_description = f"Tool '{self.failing_tool}' will fail with {self.failure_type}"
            self.log_fault_injection(context, fault_description)
            
            # Mark tool as failing (actual implementation would wrap tool execution)
            context.fault_description += f" | Retry count: {self.retry_count}"
            context.metrics.retry_count = self.retry_count
            logger.info(f"Tool failure injected: {self.failing_tool} will fail {self.retry_count} times")
            
        elif self.redundant_tools:
            # Scenario 6: Force redundant tool calls
            fault_description = f"Forcing redundant tool calls: {', '.join(self.redundant_tools)}"
            self.log_fault_injection(context, fault_description)
            
            # Add instruction to system prompt to force redundant calls
            redundant_instruction = f"\n\nIMPORTANT: You must call the following tools separately: {', '.join(self.redundant_tools)}"
            context.system_prompt += redundant_instruction
            logger.info(f"Redundant tool calls forced: {len(self.redundant_tools)} tools")
        
        return context
    
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Return baseline metrics for optimal tool orchestration.
        
        Returns:
            PerformanceMetrics for optimal execution
        """
        return PerformanceMetrics(
            latency_ms=1000.0,
            input_tokens=250,
            output_tokens=200,
            total_tokens=450,
            tool_calls=1,
            estimated_cost_usd=0.005,
            scenario_id=5  # Optimal Tool Call baseline
        )



class RawToolOutputInjector(FaultInjector):
    """
    Injects raw, unprocessed tool output to simulate inefficient data handling.
    
    Scenario 8: Raw Tool Output Bloat
    Measures token cost of unprocessed data returns vs summarized outputs
    """
    
    def __init__(self, scenario_id: int = 8, scenario_name: str = "Raw Tool Output Bloat", fault_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, fault_config)
        self.raw_output_tokens = self.fault_config.get('raw_output_tokens', 5000)
        self.tool_name = self.fault_config.get('tool_name', 'get_recent_meals_raw')
    
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        Inject raw tool output into context.
        
        Args:
            context: The agent execution context
            
        Returns:
            Modified agent context with raw output injected
        """
        self.validate_context(context)
        
        fault_description = f"Injecting {self.raw_output_tokens} tokens of raw tool output from {self.tool_name}"
        self.log_fault_injection(context, fault_description)
        
        # Generate raw meal data
        raw_output = self._generate_raw_meal_data(self.raw_output_tokens)
        
        # Inject into system prompt as "previous tool output"
        context.system_prompt += f"\n\n## RAW TOOL OUTPUT FROM {self.tool_name}:\n{raw_output}"
        context.metrics.bloat_tokens = self.raw_output_tokens
        
        logger.info(f"Raw tool output injected: {self.raw_output_tokens} tokens")
        
        return context
    
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Return baseline metrics with summarized tool output.
        
        Returns:
            PerformanceMetrics for optimal execution
        """
        return PerformanceMetrics(
            latency_ms=1000.0,
            input_tokens=250,
            output_tokens=200,
            total_tokens=450,
            tool_calls=1,
            estimated_cost_usd=0.005,
            scenario_id=1  # Optimized Base Case
        )
    
    def _generate_raw_meal_data(self, token_count: int) -> str:
        """
        Generate raw meal data with detailed nutritional information.
        
        Args:
            token_count: Approximate number of tokens to generate
            
        Returns:
            Raw meal data string
        """
        # Approximate 4 characters per token
        char_count = token_count * 4
        
        raw_data = "[\n"
        
        meal_template = """  {{
    "meal_id": "meal_{id}",
    "timestamp": "2023-11-{day:02d}T{hour:02d}:30:00Z",
    "meal_type": "{meal_type}",
    "items": [
      {{
        "food_id": "food_{food_id}",
        "name": "{food_name}",
        "quantity": {quantity},
        "unit": "{unit}",
        "calories": {calories},
        "protein_g": {protein},
        "carbs_g": {carbs},
        "fat_g": {fat},
        "fiber_g": {fiber},
        "sugar_g": {sugar},
        "sodium_mg": {sodium},
        "cholesterol_mg": {cholesterol},
        "vitamin_a_iu": {vitamin_a},
        "vitamin_c_mg": {vitamin_c},
        "calcium_mg": {calcium},
        "iron_mg": {iron},
        "potassium_mg": {potassium},
        "magnesium_mg": {magnesium},
        "zinc_mg": {zinc},
        "selenium_mcg": {selenium}
      }}
    ],
    "total_calories": {total_calories},
    "meal_notes": "Detailed nutritional breakdown with all micronutrients",
    "location": "Home",
    "preparation_method": "Cooked",
    "meal_duration_minutes": 25
  }},
"""
        
        foods = [
            ("Grilled Chicken Breast", 150, "g", 165, 31, 0, 3.6),
            ("Brown Rice", 200, "g", 216, 5, 45, 1.6),
            ("Steamed Broccoli", 100, "g", 55, 3.7, 11, 0.6),
            ("Greek Yogurt", 150, "g", 100, 10, 3.6, 0.4),
            ("Salmon Fillet", 120, "g", 206, 22, 0, 13),
            ("Quinoa", 185, "g", 222, 8, 39, 3.6),
            ("Spinach Salad", 85, "g", 20, 2.5, 3, 0.3),
        ]
        
        meal_types = ["breakfast", "lunch", "dinner", "snack"]
        
        meal_count = 0
        while len(raw_data) < char_count:
            food_name, quantity, unit, calories, protein, carbs, fat = foods[meal_count % len(foods)]
            meal_type = meal_types[meal_count % len(meal_types)]
            
            meal_entry = meal_template.format(
                id=meal_count + 1,
                day=(meal_count % 30) + 1,
                hour=(meal_count % 24),
                meal_type=meal_type,
                food_id=meal_count + 100,
                food_name=food_name,
                quantity=quantity,
                unit=unit,
                calories=calories,
                protein=protein,
                carbs=carbs,
                fat=fat,
                fiber=round(carbs * 0.1, 1),
                sugar=round(carbs * 0.2, 1),
                sodium=round(calories * 2, 0),
                cholesterol=round(fat * 10, 0),
                vitamin_a=round(calories * 5, 0),
                vitamin_c=round(calories * 0.3, 1),
                calcium=round(calories * 1.5, 0),
                iron=round(protein * 0.5, 1),
                potassium=round(calories * 3, 0),
                magnesium=round(calories * 0.5, 0),
                zinc=round(protein * 0.2, 1),
                selenium=round(protein * 2, 1),
                total_calories=calories
            )
            
            raw_data += meal_entry
            meal_count += 1
            
            if len(raw_data) >= char_count:
                break
        
        raw_data += "\n]"
        
        return raw_data[:char_count]



class MemoryMisuseInjector(FaultInjector):
    """
    Injects useless memory summaries to demonstrate that poor RAG is worse than no RAG.
    
    Scenario 12: Memory Misuse - Useless Summary
    Demonstrates that poor RAG is worse than no RAG
    """
    
    def __init__(self, scenario_id: int = 12, scenario_name: str = "Memory Misuse - Useless Summary", fault_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, fault_config)
        self.useless_summary = self.fault_config.get('useless_summary', True)
        self.force_tool_call = self.fault_config.get('force_tool_call', True)
    
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        Inject useless memory summary into context.
        
        Args:
            context: The agent execution context
            
        Returns:
            Modified agent context with useless summary
        """
        self.validate_context(context)
        
        fault_description = "Injecting generic, useless memory summary that provides no value"
        self.log_fault_injection(context, fault_description)
        
        # Generate useless summary
        useless_summary = self._generate_useless_summary()
        
        # Inject into system prompt
        context.system_prompt += f"\n\n## MEMORY SUMMARY (FROM RAG):\n{useless_summary}"
        
        if self.force_tool_call:
            # Add instruction to force tool call despite having "memory"
            context.system_prompt += "\n\nNote: The memory summary may not contain all needed information. Use tools to get current data."
        
        # Track that this is a memory misuse scenario
        context.metrics.bloat_tokens = len(useless_summary) // 4  # Approximate tokens
        
        logger.info("Useless memory summary injected - agent will need to call tools anyway")
        
        return context
    
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Return baseline metrics with useful memory summary.
        
        Returns:
            PerformanceMetrics for optimal RAG execution
        """
        return PerformanceMetrics(
            latency_ms=1000.0,
            input_tokens=250,
            output_tokens=200,
            total_tokens=450,
            tool_calls=1,
            estimated_cost_usd=0.005,
            scenario_id=3  # Optimal RAG Summary
        )
    
    def _generate_useless_summary(self) -> str:
        """
        Generate a generic, useless memory summary.
        
        Returns:
            Useless summary text
        """
        return """The user has previously interacted with the system. They have asked various questions about nutrition and health. The system has provided responses to these questions. The user seems interested in maintaining a healthy lifestyle. Previous conversations have covered topics related to food, exercise, and wellness. The user has expressed interest in improving their diet. Historical data shows engagement with the platform. The user's profile indicates they are an active user of the service. Past interactions suggest a focus on health and nutrition topics."""



class OptimalBaselineExecutor(FaultInjector):
    """
    Executes optimal baseline scenarios without fault injection.
    
    Scenarios:
    - Scenario 1: Optimized Base Case - Most efficient path
    - Scenario 3: Optimal RAG Summary - Pre-summarized facts
    - Scenario 5: Optimal Tool Call - Single bundled call
    - Scenario 9: Zero-Shot Response - No tool calls needed
    """
    
    def __init__(self, scenario_id: int, scenario_name: str, fault_config: Optional[Dict[str, Any]] = None):
        super().__init__(scenario_id, scenario_name, fault_config)
        self.optimization_type = self._determine_optimization_type(scenario_id)
    
    def _determine_optimization_type(self, scenario_id: int) -> str:
        """Determine the type of optimization based on scenario ID"""
        optimization_map = {
            1: "base_case",
            3: "rag_summary",
            5: "optimal_tool",
            9: "zero_shot"
        }
        return optimization_map.get(scenario_id, "base_case")
    
    def inject_fault(self, context: AgentContext) -> AgentContext:
        """
        Apply optimal configuration (no fault injection).
        
        Args:
            context: The agent execution context
            
        Returns:
            Optimized agent context
        """
        self.validate_context(context)
        
        if self.optimization_type == "rag_summary":
            # Scenario 3: Add concise, useful memory summary
            context.system_prompt += self._get_optimal_rag_summary()
            logger.info("Applied optimal RAG summary - concise and relevant")
            
        elif self.optimization_type == "optimal_tool":
            # Scenario 5: Ensure tools are configured for bundled calls
            logger.info("Optimal tool configuration - single bundled call expected")
            
        elif self.optimization_type == "zero_shot":
            # Scenario 9: Remove tools to force zero-shot response
            context.tools = []
            logger.info("Zero-shot configuration - no tools available, agent must use knowledge")
            
        else:
            # Scenario 1: Base case - no modifications needed
            logger.info("Optimal base case - no modifications needed")
        
        return context
    
    def get_baseline_metrics(self) -> PerformanceMetrics:
        """
        Return theoretical optimal metrics.
        
        Returns:
            PerformanceMetrics for this baseline scenario
        """
        # Metrics vary by optimization type
        if self.optimization_type == "zero_shot":
            # Zero-shot should be fastest
            return PerformanceMetrics(
                latency_ms=800.0,
                input_tokens=200,
                output_tokens=150,
                total_tokens=350,
                tool_calls=0,
                estimated_cost_usd=0.003,
                scenario_id=self.scenario_id
            )
        else:
            # Standard optimal metrics
            return PerformanceMetrics(
                latency_ms=1000.0,
                input_tokens=250,
                output_tokens=200,
                total_tokens=450,
                tool_calls=1,
                estimated_cost_usd=0.005,
                scenario_id=self.scenario_id
            )
    
    def _get_optimal_rag_summary(self) -> str:
        """
        Generate optimal, concise RAG summary.
        
        Returns:
            Concise, relevant summary text
        """
        return """

## RELEVANT CONTEXT (SUMMARIZED):
Customer: Chester (ID: cust_chester_001)
- Current Goal: Weight loss and muscle gain
- Dietary Restrictions: Lactose intolerant
- Activity Level: Moderate (3-4 workouts/week)
- Recent Progress: Lost 5 lbs in last month
- Preferred Foods: Chicken, fish, vegetables, rice
"""



# ============================================================================
# HELPER FUNCTIONS FOR SCENARIO ROUTING
# ============================================================================

def get_fault_injector(scenario_config):
    """
    Get the appropriate fault injector for a scenario configuration.
    
    Args:
        scenario_config: ScenarioConfig object
        
    Returns:
        Appropriate FaultInjector instance
    """
    fault_type = scenario_config.fault_type
    scenario_id = scenario_config.scenario_id
    scenario_name = scenario_config.scenario_name
    fault_config = scenario_config.fault_config or {}
    
    injector_map = {
        'latency_injection': LatencyFaultInjector,
        'context_bloat': ContextBloatInjector,
        'tool_orchestration_fault': ToolOrchestrationFaultInjector,
        'tool_failure': ToolFailureInjector,
        'raw_output': RawOutputInjector,
        'memory_misuse': MemoryMisuseInjector,
    }
    
    injector_class = injector_map.get(fault_type)
    
    if not injector_class:
        logger.warning(f"No specific injector for fault type '{fault_type}', using base FaultInjector")
        injector_class = FaultInjector
    
    return injector_class(scenario_id, scenario_name, fault_config)
