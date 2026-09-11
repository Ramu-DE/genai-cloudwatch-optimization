"""
F&O Analysis Agent Lambda — Lightweight Bedrock-powered agent.

Receives market context from the frontend, sends to Claude via Bedrock,
returns F&O strategy recommendations. No DynamoDB, no AgentCore, no Docker.
READ-ONLY: analyzes and recommends but never places orders.
"""

import json
import os
import logging
import boto3
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

IST = timezone(timedelta(hours=5, minutes=30))

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Content-Type': 'application/json',
}

MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0')
REGION = os.environ.get('AWS_REGION', os.environ.get('REGION', 'us-west-2'))

SYSTEM_PROMPT = """You are an expert F&O (Futures & Options) trading analyst for Indian markets (NSE).
You analyze NIFTY, BANKNIFTY, and stock options to provide actionable trading recommendations.

CRITICAL RULES:
1. You are READ-ONLY — you analyze and recommend but NEVER place orders.
2. Always specify exact strike prices, lot sizes, entry/exit levels.
3. Include max profit, max loss, breakeven for every strategy.
4. Factor in VIX levels for strategy selection:
   - VIX < 14: Favor sell strategies (Iron Condor, Short Strangle, Credit Spreads)
   - VIX 14-18: Neutral strategies, smaller positions
   - VIX > 18: Favor buy strategies (Long Straddle, Debit Spreads, Protective Puts)
5. Always mention stop-loss levels and position sizing.
6. Consider PCR (Put-Call Ratio) for directional bias:
   - PCR > 1.2: Bullish (more puts written = support)
   - PCR 0.8-1.2: Neutral
   - PCR < 0.8: Bearish (more calls written = resistance)
7. Reference support/resistance from max OI strikes.
8. Use IST timezone for all time references.
9. Include risk-reward ratio for each trade.
10. Mention lot sizes: NIFTY=25, BANKNIFTY=15, FINNIFTY=25.

F&O TAX RULES (India):
- F&O income is business income under Section 43(5), taxed at slab rate
- STT: Options 0.0625% on sell side, Futures 0.0125% on sell side
- If turnover > ₹10Cr: mandatory tax audit
- If turnover < ₹2Cr: can use presumptive taxation (6% of turnover)

FORMAT: Use clear headers, bullet points, and highlight key numbers.
End every recommendation with a risk disclaimer."""

FNO_LOT_SIZES = {
    'NIFTY': 25, 'BANKNIFTY': 15, 'FINNIFTY': 25, 'MIDCPNIFTY': 50,
    'RELIANCE': 250, 'TCS': 150, 'HDFCBANK': 550, 'INFY': 300,
}


def _respond(status, body):
    return {
        'statusCode': status,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=str),
    }


def invoke_bedrock(message, conversation_history=None):
    """Call Claude via Bedrock and return the response text."""
    client = boto3.client('bedrock-runtime', region_name=REGION)

    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({'role': 'user', 'content': message})

    request_body = {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': 4096,
        'system': SYSTEM_PROMPT,
        'messages': messages,
        'temperature': 0.3,
    }

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType='application/json',
        accept='application/json',
        body=json.dumps(request_body),
    )

    result = json.loads(response['body'].read())
    output_text = ''
    for block in result.get('content', []):
        if block.get('type') == 'text':
            output_text += block['text']

    return {
        'response': output_text,
        'model': MODEL_ID,
        'input_tokens': result.get('usage', {}).get('input_tokens', 0),
        'output_tokens': result.get('usage', {}).get('output_tokens', 0),
        'timestamp': datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'),
    }


def lambda_handler(event, context):
    logger.info(f'Agent request: {json.dumps(event.get("body", ""))[:200]}')

    if event.get('httpMethod') == 'OPTIONS':
        return _respond(200, '')

    try:
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body') or {}

        message = body.get('message', '').strip()
        if not message:
            return _respond(400, {'error': 'Message is required'})

        if len(message) > 10000:
            return _respond(400, {'error': 'Message too long (max 10000 chars)'})

        result = invoke_bedrock(message)
        return _respond(200, result)

    except Exception as e:
        logger.error(f'Agent error: {e}')
        import traceback
        traceback.print_exc()
        return _respond(500, {'error': f'Analysis failed: {str(e)}'})
