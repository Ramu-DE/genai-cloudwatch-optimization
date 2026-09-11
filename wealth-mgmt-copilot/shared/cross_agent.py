"""
Cross-Agent Orchestration for WealthAI Copilot

Allows any agent to delegate tasks to other agents via AgentCore runtime invocation.
Enables multi-agent workflows like:
  - Financial Planner asks Market Analyst for market outlook before recommending allocation
  - Tax Optimizer asks Financial Planner for portfolio details before calculating tax impact
  - Compliance Checker checks with all agents for audit completeness

Usage in a Strands agent:
    @tool
    def consult_market_analyst(query: str, client_id: str):
        return invoke_peer_agent('marcus', query, client_id)
"""

import os
import json
import time
import logging
import boto3

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')

AGENT_ARNS = {
    'marcus': os.environ.get('MARCUS_AGENT_ARN', ''),
    'sophia': os.environ.get('SOPHIA_AGENT_ARN', ''),
    'olivia': os.environ.get('OLIVIA_AGENT_ARN', ''),
    'victor': os.environ.get('VICTOR_AGENT_ARN', ''),
}

AGENT_DESCRIPTIONS = {
    'marcus': 'Market Analyst — stock analysis, sector trends, economic indicators, portfolio risk',
    'sophia': 'Financial Planner — portfolio allocation, retirement projections, rebalancing, consultations',
    'olivia': 'Tax Optimizer — tax-loss harvesting, capital gains, tax bracket management, deductions',
    'victor': 'Compliance Checker — KYC verification, AML screening, regulatory checks, audit trails',
}


def invoke_peer_agent(target_agent: str, query: str, client_id: str = 'anonymous',
                      session_id: str = '', timeout_seconds: int = 30) -> str:
    """
    Invoke a peer agent via AgentCore runtime.

    Args:
        target_agent: Agent name ('marcus', 'sophia', 'olivia', 'victor')
        query: The question/task for the peer agent
        client_id: Client context to pass through
        session_id: Session context
        timeout_seconds: Max wait time

    Returns:
        The peer agent's response text
    """
    agent_arn = AGENT_ARNS.get(target_agent.lower())
    if not agent_arn:
        return f"Agent '{target_agent}' not configured. Available: {', '.join(AGENT_ARNS.keys())}"

    try:
        client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)

        payload = {
            'prompt': query,
            'customer_id': client_id,
            'client_id': client_id,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'agent': target_agent,
            'sessionId': session_id or f'cross_agent_{int(time.time())}',
            'userId': client_id,
            'cross_agent_request': True
        }

        start = time.time()

        response = client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            qualifier='DEFAULT',
            runtimeSessionId=payload['sessionId'],
            runtimeUserId=client_id,
            payload=json.dumps(payload).encode('utf-8'),
            contentType='application/json'
        )

        duration = time.time() - start

        agent_response = ""
        if hasattr(response.get('response'), 'read'):
            data = response['response'].read()
            agent_response = data.decode('utf-8') if isinstance(data, bytes) else str(data)
        else:
            agent_response = str(response.get('response', ''))

        logger.info(f"Cross-agent call to {target_agent} completed in {duration:.2f}s")
        return agent_response

    except Exception as e:
        logger.error(f"Cross-agent call to {target_agent} failed: {e}")
        return f"Unable to reach {target_agent} agent: {str(e)}"


def get_available_agents(exclude: str = None) -> str:
    """Get list of available peer agents with descriptions"""
    agents = []
    for name, desc in AGENT_DESCRIPTIONS.items():
        if name != exclude:
            configured = "configured" if AGENT_ARNS.get(name) else "not configured"
            agents.append(f"  - {name.title()}: {desc} [{configured}]")
    return "Available peer agents:\n" + "\n".join(agents)
