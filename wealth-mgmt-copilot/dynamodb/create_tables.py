#!/usr/bin/env python3
"""Create DynamoDB tables for Wealth Management Copilot"""
import boto3
import json
import time
import os

AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')
dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)

TABLES = [
    {
        'TableName': 'wealth_mgmt_client_profiles',
        'KeySchema': [{'AttributeName': 'client_id', 'KeyType': 'HASH'}],
        'AttributeDefinitions': [{'AttributeName': 'client_id', 'AttributeType': 'S'}],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_portfolios',
        'KeySchema': [
            {'AttributeName': 'client_id', 'KeyType': 'HASH'},
            {'AttributeName': 'portfolio_id', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'client_id', 'AttributeType': 'S'},
            {'AttributeName': 'portfolio_id', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_transactions',
        'KeySchema': [
            {'AttributeName': 'client_id', 'KeyType': 'HASH'},
            {'AttributeName': 'transaction_id', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'client_id', 'AttributeType': 'S'},
            {'AttributeName': 'transaction_id', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_consultations',
        'KeySchema': [
            {'AttributeName': 'client_id', 'KeyType': 'HASH'},
            {'AttributeName': 'consultation_id', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'client_id', 'AttributeType': 'S'},
            {'AttributeName': 'consultation_id', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_advisor_schedule',
        'KeySchema': [
            {'AttributeName': 'advisor_id', 'KeyType': 'HASH'},
            {'AttributeName': 'date', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'advisor_id', 'AttributeType': 'S'},
            {'AttributeName': 'date', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_tax_records',
        'KeySchema': [
            {'AttributeName': 'client_id', 'KeyType': 'HASH'},
            {'AttributeName': 'tax_year', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'client_id', 'AttributeType': 'S'},
            {'AttributeName': 'tax_year', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_compliance_records',
        'KeySchema': [
            {'AttributeName': 'client_id', 'KeyType': 'HASH'},
            {'AttributeName': 'record_id', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'client_id', 'AttributeType': 'S'},
            {'AttributeName': 'record_id', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_audit_log',
        'KeySchema': [
            {'AttributeName': 'client_id', 'KeyType': 'HASH'},
            {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'client_id', 'AttributeType': 'S'},
            {'AttributeName': 'timestamp', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_market_data',
        'KeySchema': [
            {'AttributeName': 'ticker', 'KeyType': 'HASH'},
            {'AttributeName': 'date', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'ticker', 'AttributeType': 'S'},
            {'AttributeName': 'date', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    },
    {
        'TableName': 'wealth_mgmt_user_auth',
        'KeySchema': [{'AttributeName': 'email', 'KeyType': 'HASH'}],
        'AttributeDefinitions': [
            {'AttributeName': 'email', 'AttributeType': 'S'},
            {'AttributeName': 'session_token', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST',
        'GlobalSecondaryIndexes': [{
            'IndexName': 'session_token-index',
            'KeySchema': [{'AttributeName': 'session_token', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'}
        }]
    },
    {
        'TableName': 'wealth_mgmt_websocket_connections',
        'KeySchema': [{'AttributeName': 'connectionId', 'KeyType': 'HASH'}],
        'AttributeDefinitions': [{'AttributeName': 'connectionId', 'AttributeType': 'S'}],
        'BillingMode': 'PAY_PER_REQUEST',
        'TimeToLiveSpecification': {'Enabled': True, 'AttributeName': 'ttl'}
    },
    {
        'TableName': 'wealth_mgmt_load_test_results',
        'KeySchema': [
            {'AttributeName': 'test_id', 'KeyType': 'HASH'},
            {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'test_id', 'AttributeType': 'S'},
            {'AttributeName': 'timestamp', 'AttributeType': 'S'}
        ],
        'BillingMode': 'PAY_PER_REQUEST'
    }
]


def create_tables():
    existing = dynamodb.list_tables()['TableNames']

    for table_config in TABLES:
        name = table_config['TableName']
        if name in existing:
            print(f"  Table {name} already exists — skipping")
            continue

        ttl_spec = table_config.pop('TimeToLiveSpecification', None)

        try:
            dynamodb.create_table(**table_config)
            print(f"  Creating {name}...")

            waiter = dynamodb.get_waiter('table_exists')
            waiter.wait(TableName=name, WaiterConfig={'Delay': 2, 'MaxAttempts': 30})
            print(f"  Created {name}")

            if ttl_spec:
                dynamodb.update_time_to_live(
                    TableName=name,
                    TimeToLiveSpecification=ttl_spec
                )
        except Exception as e:
            print(f"  Error creating {name}: {e}")


if __name__ == '__main__':
    print("Creating Wealth Management DynamoDB tables...")
    create_tables()
    print("Done.")
