#!/usr/bin/env python3
"""
Victor Compliance Checker Agent - LangGraph with Flask HTTP Server
KYC verification, AML screening, regulatory compliance, and audit trail generation.
Deployed on AWS Fargate with ADOT observability.
"""
import os
import json
import logging
import boto3
import uuid
import time
from typing import Annotated
from typing_extensions import TypedDict
from decimal import Decimal
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from flask_cors import CORS

try:
    from opentelemetry import baggage
    from opentelemetry.context import attach
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    print("Warning: OpenTelemetry baggage not available - session propagation limited")

from langchain.chat_models import init_chat_model
from config_reader import get_config
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool

# CloudWatch Custom Metrics
try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
    from metrics_emitter import MetricsEmitter
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

print("=" * 60, flush=True)
print("Victor Compliance Checker Agent - Flask HTTP Server", flush=True)
print("=" * 60, flush=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.info("Loading configuration from config.conf...")
config = get_config()
AWS_REGION = config.get_aws_region()
AGENT_CONFIG = config.get_compliance_agent_config()
MODEL_ID = AGENT_CONFIG['model_id']
TABLES = config.get_dynamodb_tables()
SERVICE_NAME = AGENT_CONFIG['service_name_full']
COMPLIANCE_RULES = config.get_compliance_rules()

logger.info(f"AWS Region: {AWS_REGION}")
logger.info(f"Model ID: {MODEL_ID}")
logger.info(f"Service Name: {SERVICE_NAME}")
logger.debug(f"OTEL Available: {OTEL_AVAILABLE}")
logger.debug(f"Compliance Rules: {COMPLIANCE_RULES}")

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
logger.info("DynamoDB client initialized")

metrics = MetricsEmitter(agent_name='victor', model_id=MODEL_ID) if METRICS_AVAILABLE else None
logger.debug(f"Tables: {TABLES}")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def decimal_to_native(obj):
    """Convert Decimal objects to native Python types"""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_native(v) for v in obj]
    return obj


def log_dynamodb_request(operation, table_name, key=None, item=None):
    """Log DynamoDB request with full details"""
    logger.info("=" * 80)
    logger.info("DYNAMODB REQUEST START")
    logger.info(f"Operation: {operation}")
    logger.info(f"Table: {table_name}")
    logger.info(f"Key: {json.dumps(key, default=str) if key else 'None'}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")


def log_dynamodb_response(operation, response, duration):
    """Log DynamoDB response with full details"""
    logger.info(f"DYNAMODB RESPONSE - Operation: {operation}")
    logger.info(f"Duration: {duration:.3f}s")
    logger.info(f"HTTP Status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode', 'Unknown')}")
    logger.info(f"Items Count: {len(response.get('Items', []))}")


def write_audit_entry(client_id, action, details, result_status):
    """Write an entry to the audit log table"""
    try:
        table = dynamodb.Table(TABLES['audit_log'])
        entry = {
            'audit_id': str(uuid.uuid4()),
            'client_id': client_id,
            'action': action,
            'details': details,
            'result_status': result_status,
            'agent': 'victor_compliance',
            'timestamp': datetime.now().isoformat(),
        }
        table.put_item(Item=entry)
        logger.info(f"Audit entry written: {action} for {client_id} -> {result_status}")
    except Exception as e:
        logger.warning(f"Could not write audit entry: {e}")


# ============================================================================
# MOCK DATA (used when DynamoDB tables are not yet populated)
# ============================================================================

MOCK_CLIENTS = {
    "client_alice_morgan": {
        "client_id": "client_alice_morgan",
        "name": "Alice Morgan",
        "email": "alice.morgan@example.com",
        "phone": "+1-555-0101",
        "risk_tolerance": "moderate",
        "account_type": "individual",
        "net_worth": 1250000,
        "annual_income": 185000,
        "kyc_status": "VERIFIED",
        "kyc_verified_date": "2026-03-15",
        "kyc_expiry_date": "2027-03-15",
        "accredited_investor": True,
        "pep_status": False,
        "country": "US",
        "state": "CA",
        "tax_id_on_file": True,
    },
    "client_bob_chen": {
        "client_id": "client_bob_chen",
        "name": "Bob Chen",
        "email": "bob.chen@example.com",
        "phone": "+1-555-0202",
        "risk_tolerance": "aggressive",
        "account_type": "joint",
        "net_worth": 3500000,
        "annual_income": 420000,
        "kyc_status": "EXPIRED",
        "kyc_verified_date": "2025-01-10",
        "kyc_expiry_date": "2026-01-10",
        "accredited_investor": True,
        "pep_status": False,
        "country": "US",
        "state": "NY",
        "tax_id_on_file": True,
    },
    "client_diana_wells": {
        "client_id": "client_diana_wells",
        "name": "Diana Wells",
        "email": "diana.wells@example.com",
        "phone": "+1-555-0303",
        "risk_tolerance": "conservative",
        "account_type": "trust",
        "net_worth": 8200000,
        "annual_income": 650000,
        "kyc_status": "PENDING",
        "kyc_verified_date": None,
        "kyc_expiry_date": None,
        "accredited_investor": True,
        "pep_status": True,
        "country": "US",
        "state": "FL",
        "tax_id_on_file": False,
    },
}

MOCK_TRANSACTIONS = {
    "client_alice_morgan": [
        {"tx_id": "TX-20260901-001", "type": "BUY", "ticker": "AAPL", "amount": 15000, "shares": 65, "date": "2026-09-01", "status": "APPROVED"},
        {"tx_id": "TX-20260903-002", "type": "BUY", "ticker": "MSFT", "amount": 22000, "shares": 50, "date": "2026-09-03", "status": "APPROVED"},
        {"tx_id": "TX-20260905-003", "type": "SELL", "ticker": "TSLA", "amount": 8500, "shares": 30, "date": "2026-09-05", "status": "APPROVED"},
        {"tx_id": "TX-20260908-004", "type": "BUY", "ticker": "NVDA", "amount": 45000, "shares": 300, "date": "2026-09-08", "status": "FLAGGED"},
    ],
    "client_bob_chen": [
        {"tx_id": "TX-20260901-010", "type": "BUY", "ticker": "BTC-ETF", "amount": 75000, "shares": 1200, "date": "2026-09-01", "status": "FLAGGED"},
        {"tx_id": "TX-20260902-011", "type": "SELL", "ticker": "AMZN", "amount": 32000, "shares": 150, "date": "2026-09-02", "status": "APPROVED"},
        {"tx_id": "TX-20260902-012", "type": "BUY", "ticker": "AMZN", "amount": 31500, "shares": 148, "date": "2026-09-02", "status": "FLAGGED"},
        {"tx_id": "TX-20260905-013", "type": "TRANSFER", "ticker": None, "amount": 9800, "shares": None, "date": "2026-09-05", "status": "PENDING_REVIEW"},
        {"tx_id": "TX-20260906-014", "type": "TRANSFER", "ticker": None, "amount": 9700, "shares": None, "date": "2026-09-06", "status": "PENDING_REVIEW"},
        {"tx_id": "TX-20260907-015", "type": "TRANSFER", "ticker": None, "amount": 9900, "shares": None, "date": "2026-09-07", "status": "PENDING_REVIEW"},
    ],
    "client_diana_wells": [
        {"tx_id": "TX-20260901-020", "type": "BUY", "ticker": "VTI", "amount": 120000, "shares": 450, "date": "2026-09-01", "status": "PENDING_REVIEW"},
    ],
}

MOCK_COMPLIANCE_RECORDS = {
    "client_alice_morgan": [
        {"record_id": "CR-001", "type": "ANNUAL_REVIEW", "date": "2026-06-15", "status": "PASSED", "notes": "Annual suitability review completed. No issues found."},
        {"record_id": "CR-002", "type": "LARGE_TRADE_REVIEW", "date": "2026-09-08", "status": "UNDER_REVIEW", "notes": "NVDA purchase $45,000 exceeds review threshold."},
    ],
    "client_bob_chen": [
        {"record_id": "CR-010", "type": "AML_ALERT", "date": "2026-09-07", "status": "OPEN", "notes": "Multiple transfers near $10,000 threshold detected. Possible structuring."},
        {"record_id": "CR-011", "type": "WASH_SALE_ALERT", "date": "2026-09-02", "status": "OPEN", "notes": "AMZN sold and repurchased same day at similar price."},
    ],
    "client_diana_wells": [
        {"record_id": "CR-020", "type": "PEP_SCREENING", "date": "2026-08-20", "status": "FLAGGED", "notes": "Client flagged as Politically Exposed Person. Enhanced due diligence required."},
        {"record_id": "CR-021", "type": "KYC_INCOMPLETE", "date": "2026-09-01", "status": "OPEN", "notes": "KYC verification pending. Tax ID not on file."},
    ],
}


def get_client_data(client_id):
    """Fetch client data from DynamoDB, falling back to mock data"""
    try:
        table = dynamodb.Table(TABLES['client_profiles'])
        log_dynamodb_request("GetItem", TABLES['client_profiles'], key={"client_id": client_id})
        start = time.time()
        response = table.get_item(Key={"client_id": client_id})
        log_dynamodb_response("GetItem", response, time.time() - start)
        if 'Item' in response:
            return decimal_to_native(response['Item'])
    except Exception as e:
        logger.debug(f"DynamoDB lookup failed for {client_id}: {e}")

    clean_id = client_id.replace('client_', '') if client_id.startswith('client_') else client_id
    for mock_id, data in MOCK_CLIENTS.items():
        if clean_id in mock_id or mock_id.endswith(clean_id):
            return data
    return MOCK_CLIENTS.get(client_id)


def get_transaction_data(client_id):
    """Fetch transaction history from DynamoDB, falling back to mock data"""
    try:
        table = dynamodb.Table(TABLES['transactions'])
        log_dynamodb_request("Scan", TABLES['transactions'])
        start = time.time()
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('client_id').eq(client_id)
        )
        log_dynamodb_response("Scan", response, time.time() - start)
        items = response.get('Items', [])
        if items:
            return [decimal_to_native(i) for i in items]
    except Exception as e:
        logger.debug(f"DynamoDB transaction lookup failed for {client_id}: {e}")

    return MOCK_TRANSACTIONS.get(client_id, [])


def get_compliance_records(client_id):
    """Fetch compliance records from DynamoDB, falling back to mock data"""
    try:
        table = dynamodb.Table(TABLES['compliance_records'])
        log_dynamodb_request("Scan", TABLES['compliance_records'])
        start = time.time()
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('client_id').eq(client_id)
        )
        log_dynamodb_response("Scan", response, time.time() - start)
        items = response.get('Items', [])
        if items:
            return [decimal_to_native(i) for i in items]
    except Exception as e:
        logger.debug(f"DynamoDB compliance lookup failed for {client_id}: {e}")

    return MOCK_COMPLIANCE_RECORDS.get(client_id, [])


# ============================================================================
# LANGCHAIN TOOLS
# ============================================================================

@tool
def get_client_info(client_id: str) -> str:
    """Get client profile information including KYC status and account details.

    Args:
        client_id: The client ID (e.g., 'client_alice_morgan')

    Returns:
        Client profile with compliance-relevant details
    """
    try:
        logger.info(f"Tool: get_client_info({client_id})")
        client = get_client_data(client_id)
        if not client:
            return f"Client '{client_id}' not found in the system."

        result = f"""Client Profile: {client.get('name', 'Unknown')}
Client ID: {client.get('client_id')}
Email: {client.get('email', 'N/A')}
Phone: {client.get('phone', 'N/A')}
Account Type: {client.get('account_type', 'N/A')}
Risk Tolerance: {client.get('risk_tolerance', 'N/A')}
Net Worth: ${client.get('net_worth', 0):,.0f}
Annual Income: ${client.get('annual_income', 0):,.0f}

KYC Status: {client.get('kyc_status', 'UNKNOWN')}
KYC Verified: {client.get('kyc_verified_date', 'N/A')}
KYC Expiry: {client.get('kyc_expiry_date', 'N/A')}
Accredited Investor: {'Yes' if client.get('accredited_investor') else 'No'}
PEP Status: {'Yes - Enhanced Due Diligence Required' if client.get('pep_status') else 'No'}
Tax ID On File: {'Yes' if client.get('tax_id_on_file') else 'No - MISSING'}
State: {client.get('state', 'N/A')}, Country: {client.get('country', 'N/A')}"""

        write_audit_entry(client_id, "CLIENT_LOOKUP", f"Profile retrieved for {client.get('name')}", "COMPLETED")
        return result

    except Exception as e:
        logger.error(f"Error in get_client_info: {e}")
        return f"Error retrieving client info: {str(e)}"


@tool
def verify_kyc(client_id: str) -> str:
    """Verify KYC (Know Your Customer) status for a client. Checks identity verification,
    document expiry, PEP screening, and tax ID status.

    Args:
        client_id: The client ID to verify

    Returns:
        Detailed KYC verification report with compliance status and required actions
    """
    try:
        logger.info(f"Tool: verify_kyc({client_id})")
        client = get_client_data(client_id)
        if not client:
            return f"Client '{client_id}' not found. Cannot perform KYC verification."

        issues = []
        status = "PASS"
        kyc_status = client.get('kyc_status', 'UNKNOWN')

        if kyc_status == 'EXPIRED':
            issues.append("KYC verification has EXPIRED. Client must re-verify identity before any new transactions.")
            status = "FAIL"
        elif kyc_status == 'PENDING':
            issues.append("KYC verification is PENDING. Initial verification not yet completed.")
            status = "FAIL"
        elif kyc_status == 'VERIFIED':
            expiry = client.get('kyc_expiry_date')
            if expiry:
                expiry_date = datetime.strptime(expiry, '%Y-%m-%d')
                days_until_expiry = (expiry_date - datetime.now()).days
                if days_until_expiry < 30:
                    issues.append(f"KYC expires in {days_until_expiry} days. Renewal recommended.")
                    status = "WARNING"

        if not client.get('tax_id_on_file'):
            issues.append("Tax ID (SSN/TIN) is NOT on file. Required for IRS reporting compliance.")
            status = "FAIL"

        if client.get('pep_status'):
            issues.append("Client is a Politically Exposed Person (PEP). Enhanced due diligence required per BSA/AML regulations.")
            if status != "FAIL":
                status = "WARNING"

        if not client.get('accredited_investor') and client.get('net_worth', 0) > 1000000:
            issues.append("Net worth exceeds $1M but accredited investor status not confirmed. Verify for Regulation D eligibility.")

        result = f"""KYC Verification Report for {client.get('name')}
{'=' * 50}
Overall Status: {status}
KYC Status: {kyc_status}
Verified Date: {client.get('kyc_verified_date', 'N/A')}
Expiry Date: {client.get('kyc_expiry_date', 'N/A')}
Accredited Investor: {'Yes' if client.get('accredited_investor') else 'No'}
PEP Status: {'Yes' if client.get('pep_status') else 'No'}
Tax ID On File: {'Yes' if client.get('tax_id_on_file') else 'No'}

"""
        if issues:
            result += "Issues Found:\n"
            for i, issue in enumerate(issues, 1):
                result += f"  {i}. {issue}\n"
            result += f"\nRequired Actions:\n"
            if kyc_status in ('EXPIRED', 'PENDING'):
                result += "  - Schedule identity re-verification\n"
                result += "  - Collect updated government-issued photo ID\n"
            if not client.get('tax_id_on_file'):
                result += "  - Collect W-9 form with Tax ID\n"
            if client.get('pep_status'):
                result += "  - Complete Enhanced Due Diligence (EDD) review\n"
                result += "  - Document source of funds\n"
        else:
            result += "No issues found. Client is fully compliant."

        write_audit_entry(client_id, "KYC_VERIFICATION", f"Status: {status}, Issues: {len(issues)}", status)
        if metrics:
            metrics.emit_compliance_event("KYC_VERIFICATION", status, client_id)
        return result

    except Exception as e:
        logger.error(f"Error in verify_kyc: {e}")
        if metrics:
            metrics.emit_compliance_event("KYC_VERIFICATION", "ERROR", client_id)
        return f"Error performing KYC verification: {str(e)}"


@tool
def screen_transaction(client_id: str, transaction_type: str, amount: float, ticker: str = None) -> str:
    """Screen a proposed or completed transaction for AML (Anti-Money Laundering) compliance.
    Checks against structuring patterns, velocity limits, and suspicious activity indicators.

    Args:
        client_id: The client ID
        transaction_type: Type of transaction (BUY, SELL, TRANSFER, WITHDRAWAL)
        amount: Transaction amount in USD
        ticker: Stock/ETF ticker symbol (optional, for securities transactions)

    Returns:
        AML screening result with risk assessment and any flags
    """
    try:
        logger.info(f"Tool: screen_transaction({client_id}, {transaction_type}, ${amount:,.2f}, {ticker})")
        client = get_client_data(client_id)
        if not client:
            return f"Client '{client_id}' not found. Transaction cannot be screened."

        flags = []
        risk_level = "LOW"
        decision = "APPROVED"
        tx_history = get_transaction_data(client_id)

        if amount >= COMPLIANCE_RULES['max_single_transaction']:
            flags.append(f"Transaction amount ${amount:,.2f} exceeds single-transaction threshold of ${COMPLIANCE_RULES['max_single_transaction']:,}.")
            risk_level = "HIGH"

        threshold = COMPLIANCE_RULES['aml_structuring_threshold']
        if transaction_type in ('TRANSFER', 'WITHDRAWAL') and threshold * 0.8 <= amount < threshold:
            recent_transfers = [
                tx for tx in tx_history
                if tx.get('type') in ('TRANSFER', 'WITHDRAWAL')
                and tx.get('amount', 0) >= threshold * 0.8
            ]
            if len(recent_transfers) >= 2:
                flags.append(f"STRUCTURING ALERT: Transaction of ${amount:,.2f} is just below the ${threshold:,} CTR threshold. "
                             f"{len(recent_transfers)} similar transactions detected recently. Possible currency structuring under 31 CFR 1010.100(bbb).")
                risk_level = "CRITICAL"
                decision = "FLAGGED"

        recent_amounts = sum(tx.get('amount', 0) for tx in tx_history
                            if tx.get('date', '') >= (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
        if recent_amounts + amount > COMPLIANCE_RULES['max_daily_volume']:
            flags.append(f"Daily volume would reach ${recent_amounts + amount:,.2f}, exceeding limit of ${COMPLIANCE_RULES['max_daily_volume']:,}.")
            risk_level = "HIGH" if risk_level != "CRITICAL" else risk_level
            decision = "PENDING_REVIEW"

        if ticker and transaction_type == 'BUY':
            recent_sells = [
                tx for tx in tx_history
                if tx.get('ticker') == ticker and tx.get('type') == 'SELL'
                and tx.get('date', '') >= (datetime.now() - timedelta(days=COMPLIANCE_RULES['wash_sale_lookback_days'])).strftime('%Y-%m-%d')
            ]
            if recent_sells:
                flags.append(f"WASH SALE WARNING: {ticker} was sold within the last {COMPLIANCE_RULES['wash_sale_lookback_days']} days. "
                             f"Repurchase may trigger wash sale rule under IRC Section 1091.")
                if risk_level == "LOW":
                    risk_level = "MEDIUM"

        if client.get('kyc_status') != 'VERIFIED':
            flags.append(f"Client KYC status is '{client.get('kyc_status')}'. Transactions should be restricted until KYC is VERIFIED.")
            risk_level = "HIGH"
            decision = "BLOCKED"

        if client.get('pep_status') and amount >= 25000:
            flags.append("PEP client with large transaction. Enhanced monitoring applies.")
            if risk_level == "LOW":
                risk_level = "MEDIUM"

        result = f"""AML Transaction Screening Report
{'=' * 50}
Client: {client.get('name')} ({client_id})
Transaction: {transaction_type} {'of ' + ticker if ticker else ''} for ${amount:,.2f}
Decision: {decision}
Risk Level: {risk_level}

"""
        if flags:
            result += "Flags Raised:\n"
            for i, flag in enumerate(flags, 1):
                result += f"  {i}. {flag}\n"
        else:
            result += "No flags raised. Transaction appears compliant.\n"

        result += f"\nRegulatory References:\n"
        result += f"  - BSA/AML: Bank Secrecy Act compliance\n"
        result += f"  - CTR: Currency Transaction Report threshold ($10,000)\n"
        result += f"  - SAR: Suspicious Activity Report (if FLAGGED)\n"

        write_audit_entry(client_id, "TRANSACTION_SCREENING",
                          f"{transaction_type} ${amount:,.2f} {ticker or ''} -> {decision} ({risk_level})", decision)
        if metrics:
            metrics.emit_compliance_event("TRANSACTION_SCREENING", decision, client_id)
        return result

    except Exception as e:
        logger.error(f"Error in screen_transaction: {e}")
        if metrics:
            metrics.emit_compliance_event("TRANSACTION_SCREENING", "ERROR", client_id)
        return f"Error screening transaction: {str(e)}"


@tool
def check_compliance(client_id: str, action_type: str) -> str:
    """Check regulatory compliance for a specific action. Validates against SEC, FINRA,
    and state-level regulations.

    Args:
        client_id: The client ID
        action_type: Type of action to check (e.g., 'TRADE', 'MARGIN', 'OPTIONS', 'WITHDRAWAL', 'ACCOUNT_CHANGE')

    Returns:
        Compliance check result with any violations or required approvals
    """
    try:
        logger.info(f"Tool: check_compliance({client_id}, {action_type})")
        client = get_client_data(client_id)
        if not client:
            return f"Client '{client_id}' not found."

        violations = []
        warnings = []
        approved = True
        records = get_compliance_records(client_id)

        open_records = [r for r in records if r.get('status') in ('OPEN', 'UNDER_REVIEW', 'FLAGGED')]
        if open_records:
            for rec in open_records:
                warnings.append(f"Open compliance record: {rec.get('type')} - {rec.get('notes', 'No details')}")

        if client.get('kyc_status') != 'VERIFIED':
            violations.append(f"KYC status is '{client.get('kyc_status')}'. SEC Rule 17a-8 requires verified identity for all transactions.")
            approved = False

        if action_type in ('TRADE', 'OPTIONS', 'MARGIN'):
            if not client.get('tax_id_on_file'):
                violations.append("Tax ID not on file. IRS Form W-9 required before executing trades (IRC 3406 backup withholding).")
                approved = False

        if action_type == 'OPTIONS':
            if client.get('risk_tolerance') == 'conservative':
                violations.append("Client risk profile is 'conservative'. Options trading requires 'moderate' or 'aggressive' profile per FINRA Rule 2360.")
                approved = False
            if not client.get('accredited_investor'):
                warnings.append("Non-accredited investor. Complex options strategies may require additional suitability documentation (FINRA Rule 2111).")

        if action_type == 'MARGIN':
            if client.get('net_worth', 0) < 100000:
                violations.append("Net worth below $100,000 minimum for margin accounts. FINRA Rule 4210 margin requirements not met.")
                approved = False

        if action_type == 'WITHDRAWAL' and client.get('pep_status'):
            warnings.append("PEP client withdrawal. Enhanced monitoring and documentation required per BSA/AML.")

        status = "APPROVED" if approved else "BLOCKED"
        result = f"""Regulatory Compliance Check
{'=' * 50}
Client: {client.get('name')} ({client_id})
Action: {action_type}
Result: {status}

"""
        if violations:
            result += "Violations:\n"
            for i, v in enumerate(violations, 1):
                result += f"  {i}. {v}\n"

        if warnings:
            result += "\nWarnings:\n"
            for i, w in enumerate(warnings, 1):
                result += f"  {i}. {w}\n"

        if not violations and not warnings:
            result += "No compliance issues found. Action is permitted.\n"

        result += f"\nApplicable Regulations:\n"
        result += f"  - SEC Rule 17a-8 (Customer identification)\n"
        result += f"  - FINRA Rule 2111 (Suitability)\n"
        result += f"  - FINRA Rule 4210 (Margin requirements)\n"
        result += f"  - BSA/AML (Bank Secrecy Act)\n"

        write_audit_entry(client_id, "COMPLIANCE_CHECK",
                          f"Action: {action_type} -> {status}, Violations: {len(violations)}, Warnings: {len(warnings)}", status)
        return result

    except Exception as e:
        logger.error(f"Error in check_compliance: {e}")
        return f"Error checking compliance: {str(e)}"


@tool
def check_risk_limits(client_id: str, proposed_trade: str) -> str:
    """Check if a proposed trade violates position concentration limits or portfolio risk constraints.

    Args:
        client_id: The client ID
        proposed_trade: Description of the proposed trade (e.g., 'BUY 500 shares NVDA at $150')

    Returns:
        Risk limit assessment with position sizing analysis
    """
    try:
        logger.info(f"Tool: check_risk_limits({client_id}, '{proposed_trade}')")
        client = get_client_data(client_id)
        if not client:
            return f"Client '{client_id}' not found."

        net_worth = client.get('net_worth', 0)
        risk_tolerance = client.get('risk_tolerance', 'moderate')
        tx_history = get_transaction_data(client_id)

        max_concentration = COMPLIANCE_RULES['max_position_concentration']

        ticker_exposure = {}
        for tx in tx_history:
            t = tx.get('ticker')
            if not t:
                continue
            amt = tx.get('amount', 0)
            if tx.get('type') == 'BUY':
                ticker_exposure[t] = ticker_exposure.get(t, 0) + amt
            elif tx.get('type') == 'SELL':
                ticker_exposure[t] = ticker_exposure.get(t, 0) - amt

        issues = []
        trade_lower = proposed_trade.lower()
        estimated_amount = 0
        trade_ticker = None

        for word in proposed_trade.upper().split():
            if word.isalpha() and 1 <= len(word) <= 5 and word not in ('BUY', 'SELL', 'SHARES', 'AT', 'OF', 'FOR'):
                trade_ticker = word
                break

        parts = proposed_trade.replace('$', '').replace(',', '').split()
        numbers = [float(p) for p in parts if p.replace('.', '').isdigit()]
        if len(numbers) >= 2:
            estimated_amount = numbers[0] * numbers[1]
        elif len(numbers) == 1:
            estimated_amount = numbers[0]

        if trade_ticker and net_worth > 0:
            current_exposure = ticker_exposure.get(trade_ticker, 0)
            new_exposure = current_exposure + estimated_amount
            concentration_pct = (new_exposure / net_worth) * 100

            if concentration_pct > max_concentration:
                issues.append(
                    f"Position concentration for {trade_ticker} would be {concentration_pct:.1f}% of portfolio, "
                    f"exceeding the {max_concentration}% limit. Current exposure: ${current_exposure:,.0f}, "
                    f"proposed addition: ~${estimated_amount:,.0f}."
                )

        risk_limits = {
            'conservative': {'max_single_trade_pct': 5, 'max_equity_pct': 40},
            'moderate': {'max_single_trade_pct': 10, 'max_equity_pct': 70},
            'aggressive': {'max_single_trade_pct': 20, 'max_equity_pct': 90},
        }
        limits = risk_limits.get(risk_tolerance, risk_limits['moderate'])

        if net_worth > 0 and estimated_amount > 0:
            trade_pct = (estimated_amount / net_worth) * 100
            if trade_pct > limits['max_single_trade_pct']:
                issues.append(
                    f"Trade size ~${estimated_amount:,.0f} is {trade_pct:.1f}% of portfolio. "
                    f"Maximum single trade for '{risk_tolerance}' profile is {limits['max_single_trade_pct']}% (${net_worth * limits['max_single_trade_pct'] / 100:,.0f})."
                )

        status = "WITHIN_LIMITS" if not issues else "LIMIT_BREACH"
        result = f"""Risk Limit Assessment
{'=' * 50}
Client: {client.get('name')} ({client_id})
Risk Profile: {risk_tolerance}
Net Worth: ${net_worth:,.0f}
Proposed Trade: {proposed_trade}
Status: {status}

"""
        if trade_ticker:
            result += f"Position Analysis ({trade_ticker}):\n"
            result += f"  Current Exposure: ${ticker_exposure.get(trade_ticker, 0):,.0f}\n"
            result += f"  Estimated Trade Value: ~${estimated_amount:,.0f}\n"
            if net_worth > 0:
                result += f"  Resulting Concentration: {((ticker_exposure.get(trade_ticker, 0) + estimated_amount) / net_worth * 100):.1f}%\n"
            result += f"  Max Allowed Concentration: {max_concentration}%\n\n"

        if issues:
            result += "Limit Breaches:\n"
            for i, issue in enumerate(issues, 1):
                result += f"  {i}. {issue}\n"
            result += "\nRecommendation: Reduce trade size or obtain written client acknowledgment of concentration risk.\n"
        else:
            result += "All risk limits satisfied. Trade may proceed.\n"

        write_audit_entry(client_id, "RISK_LIMIT_CHECK",
                          f"Trade: {proposed_trade} -> {status}", status)
        return result

    except Exception as e:
        logger.error(f"Error in check_risk_limits: {e}")
        return f"Error checking risk limits: {str(e)}"


@tool
def generate_audit_report(client_id: str, date_range: str = None) -> str:
    """Generate a compliance audit report for a client. Summarizes KYC status, transaction flags,
    open compliance records, and recommended actions.

    Args:
        client_id: The client ID
        date_range: Optional date range (e.g., '2026-09-01 to 2026-09-11'). Defaults to last 30 days.

    Returns:
        Comprehensive audit report with findings and recommendations
    """
    try:
        logger.info(f"Tool: generate_audit_report({client_id}, {date_range})")
        client = get_client_data(client_id)
        if not client:
            return f"Client '{client_id}' not found."

        tx_history = get_transaction_data(client_id)
        compliance_records = get_compliance_records(client_id)

        if date_range:
            parts = date_range.replace(' to ', ',').replace(' - ', ',').split(',')
            start_date = parts[0].strip()
        else:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        recent_txs = [tx for tx in tx_history if tx.get('date', '') >= start_date]
        flagged_txs = [tx for tx in recent_txs if tx.get('status') in ('FLAGGED', 'PENDING_REVIEW')]
        approved_txs = [tx for tx in recent_txs if tx.get('status') == 'APPROVED']
        total_volume = sum(tx.get('amount', 0) for tx in recent_txs)

        open_issues = [r for r in compliance_records if r.get('status') in ('OPEN', 'UNDER_REVIEW', 'FLAGGED')]

        risk_score = 0
        if client.get('kyc_status') != 'VERIFIED':
            risk_score += 30
        if client.get('pep_status'):
            risk_score += 20
        if not client.get('tax_id_on_file'):
            risk_score += 15
        risk_score += len(flagged_txs) * 10
        risk_score += len(open_issues) * 10
        risk_score = min(risk_score, 100)

        if risk_score >= 70:
            risk_rating = "HIGH"
        elif risk_score >= 40:
            risk_rating = "MEDIUM"
        else:
            risk_rating = "LOW"

        result = f"""Compliance Audit Report
{'=' * 60}
Client: {client.get('name')} ({client_id})
Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Period: {start_date} to {datetime.now().strftime('%Y-%m-%d')}
{'=' * 60}

RISK ASSESSMENT
  Overall Risk Score: {risk_score}/100
  Risk Rating: {risk_rating}

KYC STATUS
  Verification: {client.get('kyc_status', 'UNKNOWN')}
  Last Verified: {client.get('kyc_verified_date', 'N/A')}
  Expiry: {client.get('kyc_expiry_date', 'N/A')}
  PEP: {'Yes' if client.get('pep_status') else 'No'}
  Tax ID: {'On File' if client.get('tax_id_on_file') else 'MISSING'}

TRANSACTION SUMMARY
  Total Transactions: {len(recent_txs)}
  Total Volume: ${total_volume:,.2f}
  Approved: {len(approved_txs)}
  Flagged/Pending Review: {len(flagged_txs)}

"""
        if flagged_txs:
            result += "FLAGGED TRANSACTIONS:\n"
            for tx in flagged_txs:
                result += (f"  - {tx.get('tx_id')}: {tx.get('type')} {tx.get('ticker') or 'CASH'} "
                           f"${tx.get('amount', 0):,.2f} on {tx.get('date')} [{tx.get('status')}]\n")
            result += "\n"

        if open_issues:
            result += "OPEN COMPLIANCE RECORDS:\n"
            for rec in open_issues:
                result += f"  - {rec.get('record_id')}: [{rec.get('type')}] {rec.get('notes')} (Status: {rec.get('status')})\n"
            result += "\n"

        result += "RECOMMENDATIONS:\n"
        rec_num = 1
        if client.get('kyc_status') != 'VERIFIED':
            result += f"  {rec_num}. URGENT: Complete KYC verification before allowing further transactions.\n"
            rec_num += 1
        if not client.get('tax_id_on_file'):
            result += f"  {rec_num}. Collect W-9 form and Tax ID within 30 days.\n"
            rec_num += 1
        if flagged_txs:
            result += f"  {rec_num}. Review {len(flagged_txs)} flagged transaction(s) and file SAR if warranted.\n"
            rec_num += 1
        if client.get('pep_status'):
            result += f"  {rec_num}. Complete Enhanced Due Diligence review for PEP client.\n"
            rec_num += 1
        if open_issues:
            result += f"  {rec_num}. Resolve {len(open_issues)} open compliance record(s).\n"
            rec_num += 1
        if rec_num == 1:
            result += "  No action items. Client is in good standing.\n"

        write_audit_entry(client_id, "AUDIT_REPORT_GENERATED",
                          f"Risk: {risk_rating} ({risk_score}/100), Flagged: {len(flagged_txs)}, Open Issues: {len(open_issues)}", risk_rating)
        return result

    except Exception as e:
        logger.error(f"Error in generate_audit_report: {e}")
        return f"Error generating audit report: {str(e)}"


# ============================================================================
# CROSS-AGENT CONSULTATION TOOLS
# ============================================================================

try:
    import sys as _cross_sys
    _cross_sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
    from cross_agent import invoke_peer_agent
    CROSS_AGENT_AVAILABLE = True
except ImportError:
    CROSS_AGENT_AVAILABLE = False
    logger.warning("Cross-agent module not available")


@tool
def consult_market_analyst(query: str, client_id: str = "") -> str:
    """Consult Marcus (Market Analyst) for portfolio risk data, market conditions, or stock analysis
    relevant to compliance review. Use when you need current market data to assess whether
    a client's portfolio or trade complies with risk limits or suitability rules.

    Args:
        query: The question to ask Marcus
        client_id: The client ID for context

    Returns:
        Marcus's market analysis relevant to the compliance review
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    logger.info(f"Cross-agent: consulting Marcus (Market Analyst) for client {client_id}")
    return invoke_peer_agent('marcus', query, client_id)


@tool
def consult_financial_planner(query: str, client_id: str = "") -> str:
    """Consult Sophia (Financial Planner) for portfolio allocation details, investment suitability,
    or client financial plans. Use when compliance review requires verifying that recommended
    allocations meet suitability requirements for the client's risk profile.

    Args:
        query: The question to ask Sophia
        client_id: The client ID for context

    Returns:
        Sophia's portfolio planning details relevant to compliance
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    logger.info(f"Cross-agent: consulting Sophia (Financial Planner) for client {client_id}")
    return invoke_peer_agent('sophia', query, client_id)


@tool
def consult_tax_optimizer(query: str, client_id: str = "") -> str:
    """Consult Olivia (Tax Optimizer) for tax compliance verification, wash sale rule checks,
    or tax reporting status. Use when compliance review involves tax-related regulatory requirements.

    Args:
        query: The tax compliance question to ask Olivia
        client_id: The client ID for context

    Returns:
        Olivia's tax compliance analysis
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    logger.info(f"Cross-agent: consulting Olivia (Tax Optimizer) for client {client_id}")
    return invoke_peer_agent('olivia', query, client_id)


# ============================================================================
# LANGGRAPH SETUP
# ============================================================================

llm = init_chat_model(
    model=MODEL_ID,
    model_provider="bedrock_converse",
    temperature=0.3,
    region_name=AWS_REGION
)
logger.info("LLM initialized")

tools = [get_client_info, verify_kyc, screen_transaction, check_compliance, check_risk_limits, generate_audit_report,
         consult_market_analyst, consult_financial_planner, consult_tax_optimizer]
llm_with_tools = llm.bind_tools(tools)
logger.info(f"{len(tools)} tools configured")


class State(TypedDict):
    messages: Annotated[list, add_messages]
    client_id: str
    session_id: str


def chatbot(state: State):
    """Process messages and generate responses"""
    logger.info("Chatbot node invoked")
    logger.debug(f"State keys: {list(state.keys())}")
    logger.debug(f"Message count: {len(state.get('messages', []))}")

    system_content = """You are Victor, a senior compliance officer at WealthAI Advisors.

Your expertise:
- KYC (Know Your Customer) verification and identity management
- AML (Anti-Money Laundering) transaction screening and structuring detection
- SEC and FINRA regulatory compliance
- Risk limit enforcement and position concentration analysis
- Audit trail generation and regulatory reporting

Your personality:
- Thorough and detail-oriented
- Firm but professional when flagging issues
- Always cites specific regulations and rules
- Prioritizes client protection and regulatory compliance

CRITICAL RULES:
- ALWAYS use tools before answering. Never guess about client data, transaction status, or compliance status.
- When a client ID is provided, use get_client_info FIRST to retrieve their profile.
- For any transaction inquiry, use screen_transaction to check AML compliance.
- For KYC questions, use verify_kyc for a comprehensive verification report.
- For trade proposals, use check_risk_limits to verify position limits.
- When asked about overall status, use generate_audit_report for a comprehensive view.
- Never approve a transaction without running the appropriate screening tools.

Available tools:
- get_client_info(client_id): Look up client profile and compliance details
- verify_kyc(client_id): Run comprehensive KYC verification
- screen_transaction(client_id, transaction_type, amount, ticker): AML transaction screening
- check_compliance(client_id, action_type): Check regulatory compliance for an action
- check_risk_limits(client_id, proposed_trade): Verify position and concentration limits
- generate_audit_report(client_id, date_range): Generate comprehensive compliance audit report
- consult_market_analyst(query, client_id): Ask Marcus for portfolio risk data or market conditions to assess compliance
- consult_financial_planner(query, client_id): Ask Sophia for portfolio suitability details
- consult_tax_optimizer(query, client_id): Ask Olivia for tax compliance verification

Cross-agent consultation patterns:
- When compliance review requires portfolio risk data → use consult_market_analyst
- When checking investment suitability compliance → use consult_financial_planner
- When verifying tax compliance or wash sale rules → use consult_tax_optimizer"""

    client_id = state.get('client_id', '')
    logger.debug(f"Client ID from state: {client_id}")
    if client_id and client_id != 'anonymous':
        system_content += f"""

- The client you're working with has ID: {client_id}
- When they ask about "my account", "my status", or "my transactions", use their client ID.
- DO NOT ask for their client ID - you already have it."""

    messages = [{"role": "system", "content": system_content}] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")

graph = graph_builder.compile()
logger.info("LangGraph compiled")


# ============================================================================
# FLASK HTTP SERVER
# ============================================================================

flask_app = Flask(__name__)
CORS(flask_app)


@flask_app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "agent": SERVICE_NAME,
        "framework": "langgraph",
        "tools": len(tools),
        "model": MODEL_ID
    }), 200


@flask_app.route('/', methods=['GET'])
def root():
    """Root endpoint with agent info"""
    return jsonify({
        "agent": "Victor Compliance Checker Agent",
        "description": "Regulatory compliance, KYC verification, and AML screening",
        "framework": "LangGraph",
        "tools": [t.name for t in tools],
        "endpoints": {
            "health": "/health",
            "invoke": "/invoke (POST)"
        }
    }), 200


@flask_app.route('/invoke', methods=['POST'])
def invoke_agent():
    """Agent invocation endpoint with comprehensive observability support"""
    token = None
    request_start = time.time()
    try:
        payload = request.get_json()

        prompt = payload.get('prompt', '')
        client_id = payload.get('client_id', payload.get('customerId', 'anonymous'))
        trace_id = payload.get('trace_id', payload.get('traceId', ''))

        agent_name = "victor"

        header_session_id = request.headers.get('X-Amzn-Bedrock-AgentCore-Runtime-Session-Id', '')

        if header_session_id:
            bedrock_session_id = header_session_id
            logger.debug(f"Using session ID from header: {bedrock_session_id}")
        else:
            if client_id and client_id != 'anonymous':
                clean_client = client_id.replace('client_', '') if client_id.startswith('client_') else client_id
                unique_suffix = str(uuid.uuid4()).replace('-', '')[:8]
                bedrock_session_id = f"{clean_client}_{agent_name}_{unique_suffix}"
            else:
                bedrock_session_id = f"anonymous_{agent_name}_{str(uuid.uuid4())}"

        xray_trace_id = request.headers.get('X-Amzn-Trace-Id', '')
        traceparent = request.headers.get('traceparent', '')
        tracestate = request.headers.get('tracestate', '')
        mcp_session_id = request.headers.get('mcp-session-id', '')
        baggage_header = request.headers.get('baggage', '')

        if not prompt:
            return jsonify({"error": "Missing 'prompt' in request"}), 400

        logger.info(f"Invoke: client={client_id}, session={bedrock_session_id}")
        if xray_trace_id:
            logger.info(f"X-Ray Trace ID: {xray_trace_id}")
        if traceparent:
            logger.info(f"W3C traceparent: {traceparent}")
        logger.info(f"Prompt: {prompt[:100]}...")

        if OTEL_AVAILABLE and bedrock_session_id:
            try:
                ctx = baggage.set_baggage("session.id", bedrock_session_id)
                if mcp_session_id:
                    ctx = baggage.set_baggage("mcp.session.id", mcp_session_id, context=ctx)
                if client_id and client_id != 'anonymous':
                    ctx = baggage.set_baggage("user.id", client_id, context=ctx)
                if baggage_header:
                    for item in baggage_header.split(','):
                        if '=' in item:
                            key, value = item.strip().split('=', 1)
                            ctx = baggage.set_baggage(key, value, context=ctx)
                token = attach(ctx)
                logger.info(f"OTEL baggage configured with session and context")
            except Exception as e:
                logger.warning(f"Could not set OTEL baggage: {e}")

        state = {
            "messages": [{"role": "user", "content": prompt}],
            "client_id": client_id,
            "session_id": bedrock_session_id,
        }

        result = graph.invoke(state)

        response_message = result["messages"][-1]
        response_content = response_message.content if hasattr(response_message, 'content') else str(response_message)

        logger.info(f"Response generated ({len(response_content)} chars)")

        response_data = {
            "response": response_content,
            "session_id": bedrock_session_id,
            "client_id": client_id,
            "model": MODEL_ID,
            "observability": {
                "trace_id": trace_id or xray_trace_id or traceparent,
                "session_id": bedrock_session_id,
            }
        }

        if mcp_session_id:
            response_data["observability"]["mcp_session_id"] = mcp_session_id
        if xray_trace_id:
            response_data["observability"]["xray_trace_id"] = xray_trace_id
        if traceparent:
            response_data["observability"]["traceparent"] = traceparent

        if metrics:
            request_latency = (time.time() - request_start) * 1000
            input_token_est = len(prompt) // 4
            output_token_est = len(response_content) // 4
            metrics.emit_agent_response(
                latency_ms=request_latency,
                input_tokens=input_token_est,
                output_tokens=output_token_est,
                client_id=client_id,
                session_id=bedrock_session_id
            )

        if token is not None:
            try:
                from opentelemetry.context import detach
                detach(token)
            except Exception as e:
                logger.debug(f"OTEL context cleanup: {e}")

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Error in invoke: {e}")
        if metrics:
            request_latency = (time.time() - request_start) * 1000
            metrics.emit_agent_response(latency_ms=request_latency, input_tokens=0, output_tokens=0)
        if token is not None:
            try:
                from opentelemetry.context import detach
                detach(token)
            except Exception:
                pass
        return jsonify({"error": str(e)}), 500


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting Flask HTTP server on 0.0.0.0:8080")
    flask_app.run(host='0.0.0.0', port=8080, debug=False)
