#!/usr/bin/env python3
"""Seed DynamoDB tables with initial data.

This script creates the admin account and advisor schedules.
Client profiles, portfolios, and transactions are populated
from your connected trading platform (e.g. Groww) at runtime.
"""
import boto3
import os
from datetime import datetime, timedelta

AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)


def seed_user_auth():
    """Create admin account. Client accounts are created via the Register flow."""
    table = dynamodb.Table('wealth_mgmt_user_auth')
    import hashlib

    def make_hash(password):
        salt = 'wealthmgmt2024'
        hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"{salt}:{hashed}"

    users = [
        {
            'email': 'admin@wealthai.com',
            'client_id': 'admin_001',
            'full_name': 'Admin User',
            'password_hash': make_hash('admin123'),
            'role': 'admin',
            'status': 'active',
        },
    ]
    for user in users:
        table.put_item(Item=user)
    print(f"  Seeded {len(users)} auth records")


def seed_advisor_schedule():
    """Pre-populate advisor availability for the next 14 business days."""
    table = dynamodb.Table('wealth_mgmt_advisor_schedule')
    advisors = [
        {'advisor_id': 'advisor_sophia', 'advisor_name': 'Sophia Martinez', 'specialization': 'Financial Planning'},
        {'advisor_id': 'advisor_marcus', 'advisor_name': 'Marcus Thompson', 'specialization': 'Market Analysis'},
        {'advisor_id': 'advisor_olivia', 'advisor_name': 'Olivia Park', 'specialization': 'Tax Strategy'},
        {'advisor_id': 'advisor_victor', 'advisor_name': 'Victor Hayes', 'specialization': 'Compliance'},
    ]
    base_date = datetime.now()
    for advisor in advisors:
        for day_offset in range(14):
            date = (base_date + timedelta(days=day_offset)).strftime('%Y-%m-%d')
            weekday = (base_date + timedelta(days=day_offset)).weekday()
            if weekday >= 5:
                continue
            table.put_item(Item={
                'advisor_id': advisor['advisor_id'],
                'date': date,
                'advisor_name': advisor['advisor_name'],
                'specialization': advisor['specialization'],
                'available_slots': ['09:00', '10:00', '11:00', '13:00', '14:00', '15:00', '16:00'],
                'booked_slots': []
            })
    print(f"  Seeded advisor schedules (4 advisors x ~10 days)")


if __name__ == '__main__':
    print("Seeding WealthAI initial data...")
    seed_user_auth()
    seed_advisor_schedule()
    print("Done. Client data will sync from your connected trading platform.")
