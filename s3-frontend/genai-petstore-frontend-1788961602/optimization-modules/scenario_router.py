"""
Scenario Router for Luna Agent Performance Testing

This module handles parsing scenario keywords from user input and routing
to appropriate fault injection or optimization handlers.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ScenarioConfig:
    """Configuration for a performance testing scenario"""
    scenario_id: int
    scenario_name: str
    scenario_type: str
    fault_type: str
    description: str
    expected_impact: Dict[str, Any]
    fault_config: Optional[Dict[str, Any]] = None
    optimization_config: Optional[Dict[str, Any]] = None
    baseline_scenario: Optional[int] = None
    is_baseline: bool = False


class ScenarioRouter:
    """
    Routes user requests to appropriate scenario handlers based on keyword detection.
    
    Supports scenario keywords in formats:
    - "scenario10: What nutrition plan for Chester?"
    - "model_compare: Analyze Chester's diet"
    - "cache_test: Get recent meals"
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the scenario router.
        
        Args:
            config_path: Path to scenarios.json config file. 
                        Defaults to config/scenarios.json in the same directory.
        """
        if config_path is None:
            # Default to config/scenarios.json relative to this file
            config_path = Path(__file__).parent / "config" / "scenarios.json"
        
        self.config_path = Path(config_path)
        self.scenarios = self._load_scenarios()
        
        # Build keyword mapping for quick lookup
        self.keyword_map = self._build_keyword_map()
        
        logger.info(f"ScenarioRouter initialized with {len(self.scenarios)} scenarios")
    
    def _load_scenarios(self) -> Dict[int, ScenarioConfig]:
        """Load scenario configurations from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            scenarios = {}
            for scenario_data in data.get('scenarios', []):
                scenario_id = scenario_data['id']
                
                # Determine if this is a baseline scenario
                is_baseline = scenario_data.get('baseline_scenario', False)
                if isinstance(is_baseline, bool):
                    # baseline_scenario is a boolean flag
                    pass
                else:
                    # baseline_scenario is an integer reference to another scenario
                    is_baseline = False
                
                config = ScenarioConfig(
                    scenario_id=scenario_id,
                    scenario_name=scenario_data['name'],
                    scenario_type=scenario_data['type'],
                    fault_type=scenario_data['fault_type'],
                    description=scenario_data['description'],
                    expected_impact=scenario_data['expected_impact'],
                    fault_config=scenario_data.get('fault_config'),
                    optimization_config=scenario_data.get('optimization_config'),
                    baseline_scenario=scenario_data.get('baseline_scenario') if not isinstance(scenario_data.get('baseline_scenario'), bool) else None,
                    is_baseline=is_baseline
                )
                scenarios[scenario_id] = config
            
            logger.info(f"Loaded {len(scenarios)} scenarios from {self.config_path}")
            return scenarios
            
        except FileNotFoundError:
            logger.error(f"Scenario config file not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in scenario config: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading scenarios: {e}")
            raise
    
    def _build_keyword_map(self) -> Dict[str, int]:
        """
        Build a mapping of keywords to scenario IDs for quick lookup.
        
        Supports multiple keyword formats:
        - scenario{id}: e.g., "scenario10:"
        - Friendly names: e.g., "model_compare:", "cache_test:"
        """
        keyword_map = {}
        
        for scenario_id, config in self.scenarios.items():
            # Add numeric scenario keyword
            keyword_map[f"scenario{scenario_id}"] = scenario_id
            
            # Add friendly keyword mappings for common scenarios
            name_lower = config.scenario_name.lower()
            
            if "model comparison" in name_lower:
                keyword_map["model_compare"] = scenario_id
            elif "caching strategy" in name_lower:
                keyword_map["cache_test"] = scenario_id
            elif "prompt compression" in name_lower:
                keyword_map["compress_prompt"] = scenario_id
            elif "streaming vs batch" in name_lower:
                keyword_map["streaming_test"] = scenario_id
            elif "tool call batching" in name_lower:
                keyword_map["batch_tools"] = scenario_id
            elif "token budget" in name_lower:
                keyword_map["token_budget"] = scenario_id
            elif "inference parameter" in name_lower:
                keyword_map["tune_params"] = scenario_id
            elif "conversation history" in name_lower and "optimization" in name_lower:
                keyword_map["optimize_history"] = scenario_id
            elif "guardrail" in name_lower:
                keyword_map["guardrail_test"] = scenario_id
            elif "dynamic model" in name_lower:
                keyword_map["dynamic_model"] = scenario_id
            elif "context pruning" in name_lower:
                keyword_map["prune_context"] = scenario_id
            elif "retry logic" in name_lower:
                keyword_map["retry_test"] = scenario_id
            elif "sliding window" in name_lower:
                keyword_map["sliding_window"] = scenario_id
            elif "error pattern" in name_lower:
                keyword_map["error_monitor"] = scenario_id
            elif "graceful degradation" in name_lower:
                keyword_map["degradation_test"] = scenario_id
            elif "cost-per-quality" in name_lower:
                keyword_map["cost_quality"] = scenario_id
        
        return keyword_map
    
    def parse_scenario(self, user_input: str) -> Optional[ScenarioConfig]:
        """
        Parse user input for scenario keywords and return configuration.
        
        Args:
            user_input: The user's input string
            
        Returns:
            ScenarioConfig if a scenario keyword is detected, None otherwise
            
        Examples:
            >>> router.parse_scenario("scenario10: What nutrition plan?")
            ScenarioConfig(scenario_id=10, ...)
            
            >>> router.parse_scenario("model_compare: Analyze diet")
            ScenarioConfig(scenario_id=15, ...)
            
            >>> router.parse_scenario("What nutrition plan?")
            None
        """
        # Pattern to match scenario keywords: word characters followed by colon
        pattern = r'^(\w+):\s*'
        match = re.match(pattern, user_input.strip())
        
        if not match:
            logger.debug("No scenario keyword detected in user input")
            return None
        
        keyword = match.group(1).lower()
        logger.debug(f"Detected scenario keyword: {keyword}")
        
        # Look up scenario ID from keyword
        scenario_id = self.keyword_map.get(keyword)
        
        if scenario_id is None:
            logger.warning(f"Unknown scenario keyword: {keyword}")
            return None
        
        # Get scenario configuration
        config = self.scenarios.get(scenario_id)
        
        if config is None:
            logger.error(f"Scenario ID {scenario_id} not found in configuration")
            return None
        
        logger.info(f"Scenario detected: {config.scenario_name} (ID: {scenario_id})")
        logger.info(f"  Type: {config.scenario_type}")
        logger.info(f"  Fault Type: {config.fault_type}")
        logger.info(f"  Description: {config.description}")
        
        return config
    
    def get_scenario_by_id(self, scenario_id: int) -> Optional[ScenarioConfig]:
        """
        Get scenario configuration by ID.
        
        Args:
            scenario_id: The scenario ID to retrieve
            
        Returns:
            ScenarioConfig if found, None otherwise
        """
        config = self.scenarios.get(scenario_id)
        
        if config is None:
            logger.warning(f"Scenario ID {scenario_id} not found")
        
        return config
    
    def get_baseline_scenario(self, fault_scenario_id: int) -> Optional[ScenarioConfig]:
        """
        Get the baseline scenario for a given fault injection scenario.
        
        Args:
            fault_scenario_id: The fault injection scenario ID
            
        Returns:
            ScenarioConfig of the baseline scenario, or None if not found
        """
        fault_config = self.scenarios.get(fault_scenario_id)
        
        if fault_config is None:
            logger.warning(f"Fault scenario {fault_scenario_id} not found")
            return None
        
        baseline_id = fault_config.baseline_scenario
        
        if baseline_id is None:
            logger.debug(f"Scenario {fault_scenario_id} has no baseline mapping")
            return None
        
        baseline_config = self.scenarios.get(baseline_id)
        
        if baseline_config is None:
            logger.error(f"Baseline scenario {baseline_id} not found for fault scenario {fault_scenario_id}")
            return None
        
        logger.info(f"Baseline scenario for {fault_config.scenario_name}: {baseline_config.scenario_name}")
        
        return baseline_config
    
    def get_fault_injector(self, scenario_config: ScenarioConfig):
        """
        Get the appropriate fault injector for a scenario.
        
        This method will be implemented in a future task to return
        the actual fault injector instance based on the scenario type.
        
        Args:
            scenario_config: The scenario configuration
            
        Returns:
            FaultInjector instance (to be implemented)
        """
        # Placeholder - will be implemented when FaultInjector classes are created
        logger.info(f"Getting fault injector for scenario: {scenario_config.scenario_name}")
        logger.info(f"  Fault type: {scenario_config.fault_type}")
        
        # This will return actual injector instances in future implementation
        raise NotImplementedError("Fault injector instantiation will be implemented in task 2.3")
    
    def strip_scenario_keyword(self, user_input: str) -> str:
        """
        Remove scenario keyword from user input, leaving only the actual query.
        
        Args:
            user_input: The user's input string with scenario keyword
            
        Returns:
            The input string with scenario keyword removed
            
        Example:
            >>> router.strip_scenario_keyword("scenario10: What nutrition plan?")
            "What nutrition plan?"
        """
        pattern = r'^(\w+):\s*'
        return re.sub(pattern, '', user_input.strip())
