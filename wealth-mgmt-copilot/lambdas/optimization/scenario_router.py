"""
Scenario Router for Wealth Management Agent Performance Testing

Parses scenario keywords from user input and routes to the appropriate
fault injection or optimization handler.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScenarioConfig:
    """Configuration for a performance testing scenario"""
    scenario_id: int
    scenario_name: str
    scenario_type: str          # baseline | fault_injection | optimization | validation
    fault_type: str             # none | context_bloat | tool_orchestration | ...
    description: str
    expected_impact: Dict[str, Any]
    fault_config: Optional[Dict[str, Any]] = None
    optimization_config: Optional[Dict[str, Any]] = None
    baseline_scenario: Optional[int] = None
    is_baseline: bool = False
    sample_prompt: Optional[str] = None


class ScenarioRouter:
    """
    Routes user requests to scenario handlers based on keyword detection.

    Supported keyword formats:
      - "scenario10: What is the allocation?"
      - "model_compare: Analyze the portfolio"
      - "compress: Generate a retirement plan"
    """

    KEYWORD_ALIASES = {
        'model_compare': 15,
        'model_comparison': 15,
        'compress': 16,
        'prompt_compress': 16,
        'baseline': 1,
        'context_bloat': 2,
        'rag_summary': 3,
        'crm_bloat': 4,
        'optimal_tool': 5,
        'redundant_tools': 6,
        'tool_failure': 7,
        'raw_output': 8,
        'zero_shot': 9,
        'latency_spike': 10,
        'no_tools': 11,
        'bad_memory': 12,
        'token_breach': 13,
        'observability': 14,
    }

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config" / "scenarios.json"
        self.config_path = Path(config_path)
        self.scenarios: Dict[int, ScenarioConfig] = self._load_scenarios()
        logger.info(f"ScenarioRouter initialised with {len(self.scenarios)} scenarios")

    # ------------------------------------------------------------------
    def _load_scenarios(self) -> Dict[int, ScenarioConfig]:
        with open(self.config_path, 'r') as f:
            data = json.load(f)

        scenarios: Dict[int, ScenarioConfig] = {}
        for s in data.get('scenarios', []):
            sid = s['id']
            is_bl = s.get('baseline_scenario', False)
            if isinstance(is_bl, bool):
                baseline_ref = None
            else:
                baseline_ref = int(is_bl)
                is_bl = False

            scenarios[sid] = ScenarioConfig(
                scenario_id=sid,
                scenario_name=s['name'],
                scenario_type=s['type'],
                fault_type=s.get('fault_type', 'none'),
                description=s['description'],
                expected_impact=s.get('expected_impact', {}),
                fault_config=s.get('fault_config'),
                optimization_config=s.get('optimization_config'),
                baseline_scenario=baseline_ref,
                is_baseline=bool(is_bl),
                sample_prompt=s.get('sample_prompt'),
            )
        return scenarios

    # ------------------------------------------------------------------
    def get_scenario_by_id(self, scenario_id: int) -> Optional[ScenarioConfig]:
        return self.scenarios.get(scenario_id)

    def get_baseline_for(self, scenario_id: int) -> Optional[ScenarioConfig]:
        sc = self.scenarios.get(scenario_id)
        if not sc or sc.baseline_scenario is None:
            return None
        return self.scenarios.get(sc.baseline_scenario)

    # ------------------------------------------------------------------
    def parse_input(self, user_input: str) -> tuple:
        """
        Parse user input for scenario keywords.

        Returns (scenario_config | None, cleaned_prompt)
        """
        # Pattern: scenarioN: <prompt>
        match = re.match(r'scenario(\d+)\s*:\s*(.*)', user_input, re.IGNORECASE)
        if match:
            sid = int(match.group(1))
            prompt = match.group(2).strip()
            sc = self.scenarios.get(sid)
            if sc:
                logger.info(f"Matched scenario {sid} via numeric keyword")
                return sc, prompt or sc.sample_prompt or user_input
            logger.warning(f"Scenario {sid} not found")
            return None, user_input

        # Pattern: keyword: <prompt>
        for keyword, sid in self.KEYWORD_ALIASES.items():
            pattern = rf'{keyword}\s*:\s*(.*)'
            match = re.match(pattern, user_input, re.IGNORECASE)
            if match:
                prompt = match.group(1).strip()
                sc = self.scenarios.get(sid)
                if sc:
                    logger.info(f"Matched scenario {sid} via alias '{keyword}'")
                    return sc, prompt or sc.sample_prompt or user_input
                break

        return None, user_input

    # ------------------------------------------------------------------
    def list_scenarios(self) -> list:
        return [
            {
                'id': sc.scenario_id,
                'name': sc.scenario_name,
                'type': sc.scenario_type,
                'description': sc.description,
                'expected_impact': sc.expected_impact,
            }
            for sc in sorted(self.scenarios.values(), key=lambda s: s.scenario_id)
        ]
