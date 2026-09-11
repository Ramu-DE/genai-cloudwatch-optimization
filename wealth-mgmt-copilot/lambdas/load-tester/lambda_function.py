"""
Load Tester Lambda — Wealth Management Copilot
Runs concurrent AgentCore invocations, tracks per-request metrics,
stores results in DynamoDB, and emits CloudWatch custom metrics.
"""

import json
import boto3
import time
import uuid
import os
import logging
import statistics
from datetime import datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_agentcore = boto3.client('bedrock-agentcore')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')
cloudwatch = boto3.client('cloudwatch')

AWS_REGION = os.environ.get('REGION', 'us-west-2')
LOAD_TEST_RESULTS_TABLE = os.environ.get(
    'LOAD_TEST_RESULTS_TABLE', 'wealth_mgmt_load_test_results'
)

VALID_AGENTS = ['marcus', 'sophia', 'olivia', 'victor']

DEFAULT_PROMPTS = {
    'marcus': 'Analyze NVDA stock performance and tech sector trends',
    'sophia': 'Review my portfolio allocation and recommend rebalancing for retirement',
    'olivia': 'Find tax-loss harvesting opportunities in my current portfolio',
    'victor': 'Run compliance check on recent transactions for suspicious activity',
}

DEFAULT_CLIENT_IDS = {
    'marcus': 'client_sarah_chen',
    'sophia': 'client_james_wilson',
    'olivia': 'client_sarah_chen',
    'victor': 'client_alex_rodriguez',
}


def cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Content-Type': 'application/json',
    }


def respond(status, body):
    return {
        'statusCode': status,
        'headers': cors_headers(),
        'body': json.dumps(body, default=str),
    }


def decimal_to_float(obj):
    if isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


def get_load_test_session_id(client_id, request_index):
    import hashlib
    client_name = client_id.replace('client_', '') if client_id.startswith('client_') else client_id
    ts = int(time.time() * 1000)
    rand_hex = hashlib.md5(f"{ts}_{request_index}".encode()).hexdigest()[:13]
    sid = f"lt_{client_name}_{rand_hex}"
    if len(sid) > 33:
        sid = sid[:33]
    return sid


def emit_load_test_metrics(agent_name, stats, num_requests, success_count, fail_count):
    """Emit CloudWatch custom metrics for the load test run."""
    try:
        dimensions = [{'Name': 'Agent', 'Value': agent_name}]
        timestamp = datetime.utcnow()
        metric_data = [
            {
                'MetricName': 'RequestCount',
                'Dimensions': dimensions,
                'Timestamp': timestamp,
                'Value': num_requests,
                'Unit': 'Count',
            },
            {
                'MetricName': 'SuccessCount',
                'Dimensions': dimensions,
                'Timestamp': timestamp,
                'Value': success_count,
                'Unit': 'Count',
            },
            {
                'MetricName': 'FailCount',
                'Dimensions': dimensions,
                'Timestamp': timestamp,
                'Value': fail_count,
                'Unit': 'Count',
            },
        ]
        if stats.get('avg_ms'):
            metric_data.append({
                'MetricName': 'AvgLatency',
                'Dimensions': dimensions,
                'Timestamp': timestamp,
                'Value': stats['avg_ms'],
                'Unit': 'Milliseconds',
            })
        if stats.get('p95_ms'):
            metric_data.append({
                'MetricName': 'P95Latency',
                'Dimensions': dimensions,
                'Timestamp': timestamp,
                'Value': stats['p95_ms'],
                'Unit': 'Milliseconds',
            })
        if num_requests > 0:
            error_rate = (fail_count / num_requests) * 100
            metric_data.append({
                'MetricName': 'ErrorRate',
                'Dimensions': dimensions,
                'Timestamp': timestamp,
                'Value': error_rate,
                'Unit': 'Percent',
            })

        cloudwatch.put_metric_data(
            Namespace='WealthMgmt/LoadTest',
            MetricData=metric_data,
        )
        logger.info(f"Emitted {len(metric_data)} CloudWatch metrics for {agent_name}")
    except Exception as e:
        logger.warning(f"Failed to emit CloudWatch metrics: {e}")


def calc_stats(durations_ms):
    """Calculate statistics from a list of durations in milliseconds."""
    if not durations_ms:
        return {}
    s = sorted(durations_ms)
    n = len(s)
    return {
        'count': n,
        'avg_ms': round(statistics.mean(s), 1),
        'min_ms': round(s[0], 1),
        'max_ms': round(s[-1], 1),
        'median_ms': round(statistics.median(s), 1),
        'p50_ms': round(s[int(n * 0.50)], 1),
        'p95_ms': round(s[min(int(n * 0.95), n - 1)], 1),
        'p99_ms': round(s[min(int(n * 0.99), n - 1)], 1),
        'stddev_ms': round(statistics.stdev(s), 1) if n > 1 else 0,
    }


def invoke_agent(agent_arn, prompt, client_id, idx, is_fargate=False):
    """Invoke a single agent and return timing + result."""
    session_id = get_load_test_session_id(client_id, idx)
    start = time.time()
    error = None
    response_text = ''

    try:
        if is_fargate:
            import urllib3
            http = urllib3.PoolManager()
            resp = http.request(
                'POST',
                agent_arn,
                body=json.dumps({
                    'prompt': prompt,
                    'client_id': client_id,
                    'sessionId': session_id,
                }),
                headers={'Content-Type': 'application/json'},
            )
            response_text = resp.data.decode('utf-8')[:500]
        else:
            payload = {
                'prompt': prompt,
                'client_id': client_id,
                'customer_id': client_id,
                'sessionId': session_id,
                'userId': client_id,
            }
            resp = bedrock_agentcore.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                qualifier='DEFAULT',
                runtimeSessionId=session_id,
                runtimeUserId=client_id,
                payload=json.dumps(payload).encode('utf-8'),
                contentType='application/json',
            )
            if hasattr(resp.get('response'), 'read'):
                data = resp['response'].read()
                response_text = data.decode('utf-8')[:500] if isinstance(data, bytes) else str(data)[:500]
            else:
                response_text = str(resp.get('response', ''))[:500]
    except Exception as e:
        error = str(e)

    duration_ms = round((time.time() - start) * 1000, 1)
    return {
        'index': idx,
        'duration_ms': duration_ms,
        'success': error is None,
        'error': error,
        'response_preview': response_text[:200] if response_text else None,
    }


def process_async_load_test(event):
    """Run the load test asynchronously (invoked via Lambda Event mode)."""
    test_id = event['test_id']
    agent_name = event['agent_name']
    agent_arn = event['agent_arn']
    num_requests = min(event.get('num_requests', 10), 50)
    prompt = event.get('prompt', DEFAULT_PROMPTS.get(agent_name, 'Hello'))
    client_id = event.get('client_id', DEFAULT_CLIENT_IDS.get(agent_name, 'client_sarah_chen'))
    is_fargate = agent_arn.startswith('http')

    table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
    durations = []
    success_count = 0
    fail_count = 0
    errors = []
    request_details = []

    max_workers = min(num_requests, 10)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(invoke_agent, agent_arn, prompt, client_id, i, is_fargate): i
            for i in range(num_requests)
        }
        for future in as_completed(futures):
            result = future.result()
            request_details.append(result)
            if result['success']:
                success_count += 1
                durations.append(Decimal(str(result['duration_ms'])))
            else:
                fail_count += 1
                errors.append(result['error'] or 'Unknown error')

            completed = success_count + fail_count
            if completed % max(1, num_requests // 10) == 0 or completed == num_requests:
                try:
                    table.update_item(
                        Key={'test_id': test_id, 'timestamp': event['timestamp']},
                        UpdateExpression='SET completed = :c, successful = :s, failed = :f',
                        ExpressionAttributeValues={
                            ':c': completed,
                            ':s': success_count,
                            ':f': fail_count,
                        },
                    )
                except Exception:
                    pass

    stats_dict = calc_stats([float(d) for d in durations]) if durations else {}

    try:
        table.update_item(
            Key={'test_id': test_id, 'timestamp': event['timestamp']},
            UpdateExpression=(
                'SET #status = :status, completed_at = :ts, completed = :c, '
                'successful = :s, failed = :f, stats = :st, errors = :e, durations = :d'
            ),
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'completed',
                ':ts': datetime.now().isoformat(),
                ':c': success_count + fail_count,
                ':s': success_count,
                ':f': fail_count,
                ':st': json.loads(json.dumps(stats_dict)),
                ':e': errors[:20],
                ':d': durations,
            },
        )
    except Exception as e:
        logger.error(f"Error finalizing test {test_id}: {e}")

    emit_load_test_metrics(agent_name, stats_dict, num_requests, success_count, fail_count)
    logger.info(
        f"Load test {test_id} done: {success_count}/{num_requests} success, "
        f"avg={stats_dict.get('avg_ms', 'N/A')}ms"
    )


def get_load_test_results(test_id):
    try:
        table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('test_id').eq(test_id),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get('Items', [])
        if not items:
            return respond(404, {'error': 'Test not found'})
        return respond(200, decimal_to_float(items[0]))
    except Exception as e:
        logger.error(f"Error getting results: {e}")
        return respond(500, {'error': str(e)})


# ---------- HTTP handler ----------

def lambda_handler(event, context):
    # Async background invocation
    if event.get('action') == 'process_load_test':
        process_async_load_test(event)
        return

    if event.get('httpMethod') == 'OPTIONS':
        return respond(200, '')

    try:
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', event)
    except Exception:
        body = event

    path = event.get('path', event.get('rawPath', '/'))
    method = event.get('httpMethod', 'GET')
    logger.info(f"Load tester: {method} {path}")

    if path in ('/', '/health'):
        return respond(200, {'status': 'healthy', 'service': 'WealthMgmt Load Tester'})

    if path == '/invoke' and method == 'POST':
        return handle_invoke(body)

    if path == '/load-test' and method == 'POST':
        return handle_load_test(body, context)

    if path.startswith('/load-test/') and method == 'GET':
        test_id = path.split('/')[-1]
        return get_load_test_results(test_id)

    return respond(404, {'error': 'Not found'})


def resolve_agent_arn(agent_name):
    if agent_name == 'victor':
        arn = os.environ.get('VICTOR_FARGATE_URL', os.environ.get('VICTOR_AGENT_ARN', ''))
    else:
        arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN', '')
    return arn


def handle_invoke(body):
    agent_name = body.get('agent', '').lower()
    if agent_name not in VALID_AGENTS:
        return respond(400, {'error': f'Invalid agent. Choose from: {", ".join(VALID_AGENTS)}'})

    agent_arn = body.get('agentArn') or resolve_agent_arn(agent_name)
    if not agent_arn:
        return respond(400, {'error': f'Agent ARN not configured for {agent_name}'})

    prompt = body.get('prompt', DEFAULT_PROMPTS.get(agent_name, 'Hello'))
    client_id = body.get('client_id', DEFAULT_CLIENT_IDS.get(agent_name))
    is_fargate = agent_arn.startswith('http')

    result = invoke_agent(agent_arn, prompt, client_id, 0, is_fargate)
    return respond(200, result)


def handle_load_test(body, context=None):
    agent_name = body.get('agent', '').lower()
    if agent_name not in VALID_AGENTS:
        return respond(400, {'error': f'Invalid agent. Choose from: {", ".join(VALID_AGENTS)}'})

    agent_arn = body.get('agentArn') or resolve_agent_arn(agent_name)
    if not agent_arn:
        return respond(400, {'error': f'Agent ARN not configured for {agent_name}'})

    num_requests = min(int(body.get('numRequests', 10)), 50)
    prompt = body.get('prompt', DEFAULT_PROMPTS.get(agent_name, 'Hello'))
    client_id = body.get('client_id', DEFAULT_CLIENT_IDS.get(agent_name))
    async_mode = body.get('async', True)
    is_fargate = agent_arn.startswith('http')

    test_id = str(uuid.uuid4())
    ts = datetime.now().isoformat()

    if async_mode:
        try:
            table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
            table.put_item(Item={
                'test_id': test_id,
                'timestamp': ts,
                'status': 'running',
                'agent_name': agent_name,
                'prompt': prompt[:200],
                'client_id': client_id,
                'num_requests': num_requests,
                'completed': 0,
                'successful': 0,
                'failed': 0,
                'durations': [],
                'errors': [],
                'created_at': ts,
                'ttl': int(time.time()) + 3600,
            })
        except Exception as e:
            logger.error(f"DynamoDB put error: {e}")

        try:
            fn_name = context.function_name if context and hasattr(context, 'function_name') else 'wealth_mgmt_load_tester_lambda'
            lambda_client.invoke(
                FunctionName=fn_name,
                InvocationType='Event',
                Payload=json.dumps({
                    'action': 'process_load_test',
                    'test_id': test_id,
                    'timestamp': ts,
                    'agent_name': agent_name,
                    'agent_arn': agent_arn,
                    'num_requests': num_requests,
                    'prompt': prompt,
                    'client_id': client_id,
                }),
            )
        except Exception as e:
            return respond(500, {'error': f'Failed to start async test: {e}'})

        return respond(200, {
            'test_id': test_id,
            'status': 'started',
            'num_requests': num_requests,
            'agent': agent_name,
            'message': f'Load test started with {num_requests} requests. Poll /load-test/{test_id} for results.',
        })

    # Sync fallback (small tests only)
    results_list = []
    for i in range(min(num_requests, 5)):
        results_list.append(invoke_agent(agent_arn, prompt, client_id, i, is_fargate))

    durations = [r['duration_ms'] for r in results_list if r['success']]
    stats = calc_stats(durations)
    success = sum(1 for r in results_list if r['success'])
    fail = len(results_list) - success

    emit_load_test_metrics(agent_name, stats, len(results_list), success, fail)

    return respond(200, {
        'total': len(results_list),
        'successful': success,
        'failed': fail,
        'stats': stats,
        'requests': results_list,
    })
