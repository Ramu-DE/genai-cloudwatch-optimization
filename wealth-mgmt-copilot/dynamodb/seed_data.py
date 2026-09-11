#!/usr/bin/env python3
"""Seed DynamoDB tables with sample wealth management data"""
import boto3
import json
import os
from decimal import Decimal
from datetime import datetime, timedelta

AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)


def seed_client_profiles():
    table = dynamodb.Table('wealth_mgmt_client_profiles')
    clients = [
        {
            'client_id': 'client_sarah_chen',
            'full_name': 'Sarah Chen',
            'email': 'sarah.chen@email.com',
            'phone': '+1-415-555-0101',
            'risk_tolerance': 'aggressive',
            'investment_goals': ['growth', 'retirement', 'wealth_accumulation'],
            'annual_income': Decimal('285000'),
            'net_worth': Decimal('2450000'),
            'age': 38,
            'filing_status': 'married_filing_jointly',
            'tax_bracket': Decimal('32'),
            'retirement_target_age': 60,
            'monthly_contribution': Decimal('8500'),
            'kyc_status': 'VERIFIED',
            'kyc_verified_date': '2024-03-15',
            'created_at': '2023-06-15T10:00:00',
            'status': 'active'
        },
        {
            'client_id': 'client_james_wilson',
            'full_name': 'James Wilson',
            'email': 'james.wilson@email.com',
            'phone': '+1-212-555-0202',
            'risk_tolerance': 'moderate',
            'investment_goals': ['retirement', 'education_fund', 'income'],
            'annual_income': Decimal('175000'),
            'net_worth': Decimal('1200000'),
            'age': 52,
            'filing_status': 'married_filing_jointly',
            'tax_bracket': Decimal('24'),
            'retirement_target_age': 65,
            'monthly_contribution': Decimal('5000'),
            'kyc_status': 'VERIFIED',
            'kyc_verified_date': '2024-01-10',
            'created_at': '2023-01-20T14:30:00',
            'status': 'active'
        },
        {
            'client_id': 'client_priya_patel',
            'full_name': 'Priya Patel',
            'email': 'priya.patel@email.com',
            'phone': '+1-408-555-0303',
            'risk_tolerance': 'conservative',
            'investment_goals': ['capital_preservation', 'income', 'estate_planning'],
            'annual_income': Decimal('420000'),
            'net_worth': Decimal('8500000'),
            'age': 62,
            'filing_status': 'single',
            'tax_bracket': Decimal('35'),
            'retirement_target_age': 67,
            'monthly_contribution': Decimal('15000'),
            'kyc_status': 'VERIFIED',
            'kyc_verified_date': '2023-11-20',
            'created_at': '2022-08-10T09:15:00',
            'status': 'active'
        },
        {
            'client_id': 'client_alex_rodriguez',
            'full_name': 'Alex Rodriguez',
            'email': 'alex.rodriguez@email.com',
            'phone': '+1-305-555-0404',
            'risk_tolerance': 'aggressive',
            'investment_goals': ['growth', 'speculation', 'early_retirement'],
            'annual_income': Decimal('150000'),
            'net_worth': Decimal('680000'),
            'age': 29,
            'filing_status': 'single',
            'tax_bracket': Decimal('24'),
            'retirement_target_age': 45,
            'monthly_contribution': Decimal('6000'),
            'kyc_status': 'VERIFIED',
            'kyc_verified_date': '2024-06-01',
            'created_at': '2024-05-01T11:00:00',
            'status': 'active'
        },
        {
            'client_id': 'client_maria_johnson',
            'full_name': 'Maria Johnson',
            'email': 'maria.johnson@email.com',
            'phone': '+1-773-555-0505',
            'risk_tolerance': 'moderate',
            'investment_goals': ['home_purchase', 'education_fund', 'retirement'],
            'annual_income': Decimal('125000'),
            'net_worth': Decimal('350000'),
            'age': 34,
            'filing_status': 'head_of_household',
            'tax_bracket': Decimal('22'),
            'retirement_target_age': 65,
            'monthly_contribution': Decimal('3500'),
            'kyc_status': 'PENDING',
            'created_at': '2024-08-20T16:00:00',
            'status': 'active'
        }
    ]
    for client in clients:
        table.put_item(Item=client)
    print(f"  Seeded {len(clients)} client profiles")


def seed_portfolios():
    table = dynamodb.Table('wealth_mgmt_portfolios')
    portfolios = [
        {
            'client_id': 'client_sarah_chen',
            'portfolio_id': 'port_sarah_growth',
            'portfolio_name': 'Growth Portfolio',
            'portfolio_type': 'taxable',
            'total_value': Decimal('1250000'),
            'holdings': [
                {'ticker': 'AAPL', 'shares': Decimal('150'), 'avg_cost': Decimal('145.50'), 'current_price': Decimal('227.80'), 'sector': 'Technology'},
                {'ticker': 'MSFT', 'shares': Decimal('100'), 'avg_cost': Decimal('280.00'), 'current_price': Decimal('415.20'), 'sector': 'Technology'},
                {'ticker': 'AMZN', 'shares': Decimal('80'), 'avg_cost': Decimal('130.00'), 'current_price': Decimal('186.50'), 'sector': 'Consumer Discretionary'},
                {'ticker': 'GOOGL', 'shares': Decimal('120'), 'avg_cost': Decimal('110.00'), 'current_price': Decimal('175.30'), 'sector': 'Technology'},
                {'ticker': 'NVDA', 'shares': Decimal('200'), 'avg_cost': Decimal('45.00'), 'current_price': Decimal('138.70'), 'sector': 'Technology'},
                {'ticker': 'TSLA', 'shares': Decimal('60'), 'avg_cost': Decimal('240.00'), 'current_price': Decimal('248.50'), 'sector': 'Consumer Discretionary'},
                {'ticker': 'JPM', 'shares': Decimal('80'), 'avg_cost': Decimal('150.00'), 'current_price': Decimal('205.40'), 'sector': 'Financials'},
                {'ticker': 'VTI', 'shares': Decimal('300'), 'avg_cost': Decimal('210.00'), 'current_price': Decimal('265.80'), 'sector': 'Broad Market ETF'}
            ],
            'target_allocation': {'stocks': Decimal('80'), 'bonds': Decimal('15'), 'alternatives': Decimal('5')},
            'current_allocation': {'stocks': Decimal('85'), 'bonds': Decimal('10'), 'alternatives': Decimal('5')},
            'ytd_return': Decimal('18.5'),
            'last_rebalanced': '2024-06-15'
        },
        {
            'client_id': 'client_sarah_chen',
            'portfolio_id': 'port_sarah_retirement',
            'portfolio_name': '401(k) Retirement',
            'portfolio_type': 'retirement_401k',
            'total_value': Decimal('850000'),
            'holdings': [
                {'ticker': 'VTI', 'shares': Decimal('500'), 'avg_cost': Decimal('195.00'), 'current_price': Decimal('265.80'), 'sector': 'Broad Market ETF'},
                {'ticker': 'VXUS', 'shares': Decimal('400'), 'avg_cost': Decimal('52.00'), 'current_price': Decimal('58.90'), 'sector': 'International ETF'},
                {'ticker': 'BND', 'shares': Decimal('600'), 'avg_cost': Decimal('74.00'), 'current_price': Decimal('72.50'), 'sector': 'Bond ETF'},
                {'ticker': 'VNQ', 'shares': Decimal('150'), 'avg_cost': Decimal('82.00'), 'current_price': Decimal('88.40'), 'sector': 'Real Estate ETF'}
            ],
            'target_allocation': {'stocks': Decimal('70'), 'bonds': Decimal('20'), 'alternatives': Decimal('10')},
            'current_allocation': {'stocks': Decimal('72'), 'bonds': Decimal('18'), 'alternatives': Decimal('10')},
            'ytd_return': Decimal('14.2'),
            'last_rebalanced': '2024-09-01'
        },
        {
            'client_id': 'client_james_wilson',
            'portfolio_id': 'port_james_balanced',
            'portfolio_name': 'Balanced Portfolio',
            'portfolio_type': 'taxable',
            'total_value': Decimal('750000'),
            'holdings': [
                {'ticker': 'VTI', 'shares': Decimal('400'), 'avg_cost': Decimal('200.00'), 'current_price': Decimal('265.80'), 'sector': 'Broad Market ETF'},
                {'ticker': 'BND', 'shares': Decimal('800'), 'avg_cost': Decimal('75.00'), 'current_price': Decimal('72.50'), 'sector': 'Bond ETF'},
                {'ticker': 'VIG', 'shares': Decimal('300'), 'avg_cost': Decimal('155.00'), 'current_price': Decimal('182.30'), 'sector': 'Dividend ETF'},
                {'ticker': 'SCHD', 'shares': Decimal('250'), 'avg_cost': Decimal('72.00'), 'current_price': Decimal('81.50'), 'sector': 'Dividend ETF'},
                {'ticker': 'GLD', 'shares': Decimal('50'), 'avg_cost': Decimal('180.00'), 'current_price': Decimal('235.60'), 'sector': 'Commodities'}
            ],
            'target_allocation': {'stocks': Decimal('60'), 'bonds': Decimal('30'), 'alternatives': Decimal('10')},
            'current_allocation': {'stocks': Decimal('58'), 'bonds': Decimal('32'), 'alternatives': Decimal('10')},
            'ytd_return': Decimal('11.8'),
            'last_rebalanced': '2024-07-20'
        },
        {
            'client_id': 'client_priya_patel',
            'portfolio_id': 'port_priya_income',
            'portfolio_name': 'Income Portfolio',
            'portfolio_type': 'taxable',
            'total_value': Decimal('5200000'),
            'holdings': [
                {'ticker': 'BND', 'shares': Decimal('5000'), 'avg_cost': Decimal('76.00'), 'current_price': Decimal('72.50'), 'sector': 'Bond ETF'},
                {'ticker': 'VCIT', 'shares': Decimal('3000'), 'avg_cost': Decimal('82.00'), 'current_price': Decimal('80.20'), 'sector': 'Corporate Bond ETF'},
                {'ticker': 'VIG', 'shares': Decimal('800'), 'avg_cost': Decimal('148.00'), 'current_price': Decimal('182.30'), 'sector': 'Dividend ETF'},
                {'ticker': 'SCHD', 'shares': Decimal('1000'), 'avg_cost': Decimal('68.00'), 'current_price': Decimal('81.50'), 'sector': 'Dividend ETF'},
                {'ticker': 'O', 'shares': Decimal('500'), 'avg_cost': Decimal('55.00'), 'current_price': Decimal('58.70'), 'sector': 'REIT'},
                {'ticker': 'MUB', 'shares': Decimal('2000'), 'avg_cost': Decimal('108.00'), 'current_price': Decimal('106.80'), 'sector': 'Municipal Bond ETF'},
                {'ticker': 'TLT', 'shares': Decimal('1500'), 'avg_cost': Decimal('98.00'), 'current_price': Decimal('92.30'), 'sector': 'Treasury Bond ETF'}
            ],
            'target_allocation': {'stocks': Decimal('30'), 'bonds': Decimal('55'), 'alternatives': Decimal('15')},
            'current_allocation': {'stocks': Decimal('28'), 'bonds': Decimal('57'), 'alternatives': Decimal('15')},
            'ytd_return': Decimal('7.2'),
            'last_rebalanced': '2024-08-01'
        },
        {
            'client_id': 'client_alex_rodriguez',
            'portfolio_id': 'port_alex_aggressive',
            'portfolio_name': 'High Growth Portfolio',
            'portfolio_type': 'taxable',
            'total_value': Decimal('480000'),
            'holdings': [
                {'ticker': 'NVDA', 'shares': Decimal('300'), 'avg_cost': Decimal('35.00'), 'current_price': Decimal('138.70'), 'sector': 'Technology'},
                {'ticker': 'AMD', 'shares': Decimal('200'), 'avg_cost': Decimal('95.00'), 'current_price': Decimal('155.20'), 'sector': 'Technology'},
                {'ticker': 'PLTR', 'shares': Decimal('500'), 'avg_cost': Decimal('18.00'), 'current_price': Decimal('42.80'), 'sector': 'Technology'},
                {'ticker': 'COIN', 'shares': Decimal('80'), 'avg_cost': Decimal('180.00'), 'current_price': Decimal('165.30'), 'sector': 'Financials'},
                {'ticker': 'SOFI', 'shares': Decimal('1000'), 'avg_cost': Decimal('8.50'), 'current_price': Decimal('12.40'), 'sector': 'Financials'},
                {'ticker': 'ARKK', 'shares': Decimal('150'), 'avg_cost': Decimal('42.00'), 'current_price': Decimal('52.80'), 'sector': 'Innovation ETF'}
            ],
            'target_allocation': {'stocks': Decimal('95'), 'bonds': Decimal('0'), 'alternatives': Decimal('5')},
            'current_allocation': {'stocks': Decimal('97'), 'bonds': Decimal('0'), 'alternatives': Decimal('3')},
            'ytd_return': Decimal('32.4'),
            'last_rebalanced': '2024-04-10'
        }
    ]
    for portfolio in portfolios:
        table.put_item(Item=portfolio)
    print(f"  Seeded {len(portfolios)} portfolios")


def seed_transactions():
    table = dynamodb.Table('wealth_mgmt_transactions')
    transactions = [
        {'client_id': 'client_sarah_chen', 'transaction_id': 'txn_001', 'type': 'BUY', 'ticker': 'NVDA', 'shares': Decimal('50'), 'price': Decimal('120.50'), 'total': Decimal('6025.00'), 'date': '2024-09-01', 'status': 'COMPLETED', 'portfolio_id': 'port_sarah_growth'},
        {'client_id': 'client_sarah_chen', 'transaction_id': 'txn_002', 'type': 'SELL', 'ticker': 'TSLA', 'shares': Decimal('20'), 'price': Decimal('255.00'), 'total': Decimal('5100.00'), 'date': '2024-09-05', 'status': 'COMPLETED', 'portfolio_id': 'port_sarah_growth'},
        {'client_id': 'client_sarah_chen', 'transaction_id': 'txn_003', 'type': 'BUY', 'ticker': 'MSFT', 'shares': Decimal('25'), 'price': Decimal('405.00'), 'total': Decimal('10125.00'), 'date': '2024-09-10', 'status': 'COMPLETED', 'portfolio_id': 'port_sarah_growth'},
        {'client_id': 'client_james_wilson', 'transaction_id': 'txn_004', 'type': 'BUY', 'ticker': 'SCHD', 'shares': Decimal('100'), 'price': Decimal('79.00'), 'total': Decimal('7900.00'), 'date': '2024-08-15', 'status': 'COMPLETED', 'portfolio_id': 'port_james_balanced'},
        {'client_id': 'client_james_wilson', 'transaction_id': 'txn_005', 'type': 'DIVIDEND', 'ticker': 'VIG', 'shares': Decimal('0'), 'price': Decimal('0'), 'total': Decimal('850.00'), 'date': '2024-09-01', 'status': 'COMPLETED', 'portfolio_id': 'port_james_balanced'},
        {'client_id': 'client_priya_patel', 'transaction_id': 'txn_006', 'type': 'BUY', 'ticker': 'MUB', 'shares': Decimal('500'), 'price': Decimal('107.00'), 'total': Decimal('53500.00'), 'date': '2024-09-08', 'status': 'COMPLETED', 'portfolio_id': 'port_priya_income'},
        {'client_id': 'client_alex_rodriguez', 'transaction_id': 'txn_007', 'type': 'BUY', 'ticker': 'PLTR', 'shares': Decimal('200'), 'price': Decimal('40.50'), 'total': Decimal('8100.00'), 'date': '2024-09-12', 'status': 'COMPLETED', 'portfolio_id': 'port_alex_aggressive'},
        {'client_id': 'client_alex_rodriguez', 'transaction_id': 'txn_008', 'type': 'BUY', 'ticker': 'COIN', 'shares': Decimal('30'), 'price': Decimal('170.00'), 'total': Decimal('5100.00'), 'date': '2024-09-14', 'status': 'FLAGGED', 'portfolio_id': 'port_alex_aggressive', 'flag_reason': 'Concentrated position exceeds 15% of portfolio'},
    ]
    for txn in transactions:
        table.put_item(Item=txn)
    print(f"  Seeded {len(transactions)} transactions")


def seed_user_auth():
    table = dynamodb.Table('wealth_mgmt_user_auth')
    import hashlib
    def make_hash(password):
        salt = 'wealthmgmt2024'
        hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"{salt}:{hashed}"

    users = [
        {'email': 'sarah.chen@email.com', 'client_id': 'client_sarah_chen', 'full_name': 'Sarah Chen', 'password_hash': make_hash('demo123'), 'role': 'client', 'status': 'active'},
        {'email': 'james.wilson@email.com', 'client_id': 'client_james_wilson', 'full_name': 'James Wilson', 'password_hash': make_hash('demo123'), 'role': 'client', 'status': 'active'},
        {'email': 'priya.patel@email.com', 'client_id': 'client_priya_patel', 'full_name': 'Priya Patel', 'password_hash': make_hash('demo123'), 'role': 'client', 'status': 'active'},
        {'email': 'alex.rodriguez@email.com', 'client_id': 'client_alex_rodriguez', 'full_name': 'Alex Rodriguez', 'password_hash': make_hash('demo123'), 'role': 'client', 'status': 'active'},
        {'email': 'maria.johnson@email.com', 'client_id': 'client_maria_johnson', 'full_name': 'Maria Johnson', 'password_hash': make_hash('demo123'), 'role': 'client', 'status': 'active'},
        {'email': 'admin@wealthai.com', 'client_id': 'admin_001', 'full_name': 'Admin User', 'password_hash': make_hash('admin123'), 'role': 'admin', 'status': 'active'},
    ]
    for user in users:
        table.put_item(Item=user)
    print(f"  Seeded {len(users)} auth records")


def seed_advisor_schedule():
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


def seed_tax_records():
    table = dynamodb.Table('wealth_mgmt_tax_records')
    records = [
        {
            'client_id': 'client_sarah_chen',
            'tax_year': '2024',
            'filing_status': 'married_filing_jointly',
            'federal_bracket': Decimal('32'),
            'state_bracket': Decimal('9.3'),
            'short_term_gains': Decimal('12500'),
            'long_term_gains': Decimal('45000'),
            'dividend_income': Decimal('8200'),
            'realized_losses': Decimal('3200'),
            'estimated_tax_liability': Decimal('85000'),
            'charitable_contributions': Decimal('15000'),
            'ira_contributions': Decimal('7000'),
            '401k_contributions': Decimal('23000')
        },
        {
            'client_id': 'client_james_wilson',
            'tax_year': '2024',
            'filing_status': 'married_filing_jointly',
            'federal_bracket': Decimal('24'),
            'state_bracket': Decimal('6.5'),
            'short_term_gains': Decimal('3500'),
            'long_term_gains': Decimal('18000'),
            'dividend_income': Decimal('12500'),
            'realized_losses': Decimal('1800'),
            'estimated_tax_liability': Decimal('42000'),
            'charitable_contributions': Decimal('8000'),
            'ira_contributions': Decimal('7000'),
            '401k_contributions': Decimal('23000')
        },
        {
            'client_id': 'client_priya_patel',
            'tax_year': '2024',
            'filing_status': 'single',
            'federal_bracket': Decimal('35'),
            'state_bracket': Decimal('9.3'),
            'short_term_gains': Decimal('5000'),
            'long_term_gains': Decimal('25000'),
            'dividend_income': Decimal('95000'),
            'realized_losses': Decimal('8500'),
            'estimated_tax_liability': Decimal('165000'),
            'charitable_contributions': Decimal('50000'),
            'ira_contributions': Decimal('7000'),
            '401k_contributions': Decimal('0')
        }
    ]
    for record in records:
        table.put_item(Item=record)
    print(f"  Seeded {len(records)} tax records")


def seed_compliance_records():
    table = dynamodb.Table('wealth_mgmt_compliance_records')
    records = [
        {'client_id': 'client_sarah_chen', 'record_id': 'comp_001', 'type': 'KYC_VERIFICATION', 'status': 'APPROVED', 'date': '2024-03-15', 'notes': 'Identity verified via government ID and utility bill', 'reviewer': 'compliance_team'},
        {'client_id': 'client_james_wilson', 'record_id': 'comp_002', 'type': 'KYC_VERIFICATION', 'status': 'APPROVED', 'date': '2024-01-10', 'notes': 'Identity verified', 'reviewer': 'compliance_team'},
        {'client_id': 'client_alex_rodriguez', 'record_id': 'comp_003', 'type': 'TRANSACTION_REVIEW', 'status': 'FLAGGED', 'date': '2024-09-14', 'notes': 'High concentration in single position (COIN). Exceeds 15% threshold.', 'reviewer': 'auto_monitor'},
        {'client_id': 'client_maria_johnson', 'record_id': 'comp_004', 'type': 'KYC_VERIFICATION', 'status': 'PENDING', 'date': '2024-08-20', 'notes': 'Awaiting additional documentation', 'reviewer': 'compliance_team'},
        {'client_id': 'client_priya_patel', 'record_id': 'comp_005', 'type': 'SUITABILITY_REVIEW', 'status': 'APPROVED', 'date': '2024-08-01', 'notes': 'Conservative allocation aligned with risk profile and age', 'reviewer': 'advisor_sophia'},
    ]
    for record in records:
        table.put_item(Item=record)
    print(f"  Seeded {len(records)} compliance records")


if __name__ == '__main__':
    print("Seeding Wealth Management data...")
    seed_client_profiles()
    seed_portfolios()
    seed_transactions()
    seed_user_auth()
    seed_advisor_schedule()
    seed_tax_records()
    seed_compliance_records()
    print("Done.")
