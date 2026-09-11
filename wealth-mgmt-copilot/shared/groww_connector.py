"""
Groww Portfolio Connector — Read-Only Integration

Connects to Groww (Indian brokerage) to fetch real portfolio data.
Supports: Stocks (NSE/BSE), Mutual Funds, Gold, FDs.

Usage:
    connector = GrowwConnector(auth_token="...")
    holdings = connector.get_holdings()
    mf = connector.get_mutual_funds()
    orders = connector.get_order_history()

Data is normalized to the WealthAI Copilot schema and written to DynamoDB
for agents to access via their existing tools.
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
import requests

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')

GROWW_BASE_URL = "https://groww.in/v1/api"
GROWW_STOCK_URL = f"{GROWW_BASE_URL}/stocks_data"
GROWW_MF_URL = f"{GROWW_BASE_URL}/v1/mutual-fund"
GROWW_ORDER_URL = f"{GROWW_BASE_URL}/order"
GROWW_HOLDING_URL = f"{GROWW_BASE_URL}/v2/user/stocks/holdings"
GROWW_POSITIONS_URL = f"{GROWW_BASE_URL}/v2/user/stocks/positions"

NSE_SECTOR_MAP = {
    'RELIANCE': 'Energy', 'TCS': 'Technology', 'INFY': 'Technology',
    'HDFCBANK': 'Banking', 'ICICIBANK': 'Banking', 'SBIN': 'Banking',
    'BHARTIARTL': 'Telecom', 'ITC': 'FMCG', 'HINDUNILVR': 'FMCG',
    'LT': 'Infrastructure', 'BAJFINANCE': 'Finance', 'MARUTI': 'Auto',
    'TATAMOTORS': 'Auto', 'HCLTECH': 'Technology', 'WIPRO': 'Technology',
    'ASIANPAINT': 'Consumer', 'SUNPHARMA': 'Pharma', 'DRREDDY': 'Pharma',
    'ADANIENT': 'Conglomerate', 'TATASTEEL': 'Metals', 'JSWSTEEL': 'Metals',
    'POWERGRID': 'Power', 'NTPC': 'Power', 'COALINDIA': 'Mining',
    'TITAN': 'Consumer', 'BAJAJFINSV': 'Finance', 'ULTRACEMCO': 'Cement',
    'ONGC': 'Energy', 'NESTLEIND': 'FMCG', 'TECHM': 'Technology',
}

INR_TO_USD = 0.012


class GrowwConnector:
    """Read-only connector to Groww brokerage platform."""

    def __init__(self, auth_token: str = None, access_token: str = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

        if auth_token:
            self.session.headers['Authorization'] = f'Bearer {auth_token}'
        if access_token:
            self.session.headers['x-access-token'] = access_token

        self.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

    def _get(self, url: str, params: dict = None) -> dict:
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Groww API error: {e}")
            return {}

    # ── Stock Holdings ──────────────────────────────────────────────

    def get_holdings(self) -> list:
        """Fetch all stock holdings from Groww demat account."""
        data = self._get(GROWW_HOLDING_URL)
        if not data:
            return []

        holdings = []
        for h in data.get('holdingData', data.get('holdings', [])):
            holding = {
                'ticker': h.get('tradingSymbol', h.get('symbol', '')),
                'exchange': h.get('exchange', 'NSE'),
                'company_name': h.get('companyName', ''),
                'quantity': int(h.get('quantity', 0)),
                'avg_price': float(h.get('averagePrice', h.get('avgPrice', 0))),
                'current_price': float(h.get('lastTradedPrice', h.get('ltp', 0))),
                'invested_value': float(h.get('investedValue', 0)),
                'current_value': float(h.get('currentValue', 0)),
                'pnl': float(h.get('unrealisedProfitLoss', h.get('pnl', 0))),
                'pnl_percent': float(h.get('unrealisedProfitLossPercentage', 0)),
                'sector': NSE_SECTOR_MAP.get(h.get('tradingSymbol', ''), 'Other'),
                'day_change': float(h.get('dayChange', 0)),
                'day_change_percent': float(h.get('dayChangePercentage', 0)),
            }
            if holding['invested_value'] == 0 and holding['quantity'] > 0:
                holding['invested_value'] = holding['quantity'] * holding['avg_price']
            if holding['current_value'] == 0 and holding['quantity'] > 0:
                holding['current_value'] = holding['quantity'] * holding['current_price']

            holdings.append(holding)

        return holdings

    def get_positions(self) -> list:
        """Fetch intraday/open positions."""
        data = self._get(GROWW_POSITIONS_URL)
        if not data:
            return []

        positions = []
        for p in data.get('positionData', data.get('positions', [])):
            positions.append({
                'ticker': p.get('tradingSymbol', ''),
                'exchange': p.get('exchange', 'NSE'),
                'quantity': int(p.get('quantity', 0)),
                'buy_price': float(p.get('buyPrice', 0)),
                'sell_price': float(p.get('sellPrice', 0)),
                'pnl': float(p.get('pnl', 0)),
                'product_type': p.get('productType', 'CNC'),
            })
        return positions

    # ── Mutual Funds ────────────────────────────────────────────────

    def get_mutual_funds(self) -> list:
        """Fetch mutual fund investments."""
        data = self._get(f"{GROWW_MF_URL}/user/investments")
        if not data:
            return []

        funds = []
        for f in data.get('investments', data.get('mutualFunds', [])):
            funds.append({
                'scheme_name': f.get('schemeName', f.get('fundName', '')),
                'fund_house': f.get('fundHouse', ''),
                'category': f.get('category', ''),
                'invested_value': float(f.get('investedValue', 0)),
                'current_value': float(f.get('currentValue', 0)),
                'returns_percent': float(f.get('absoluteReturn', 0)),
                'xirr': float(f.get('xirr', 0)),
                'units': float(f.get('units', 0)),
                'nav': float(f.get('nav', 0)),
                'sip_active': f.get('sipActive', False),
                'sip_amount': float(f.get('sipAmount', 0)),
            })
        return funds

    # ── Order History ───────────────────────────────────────────────

    def get_order_history(self, days: int = 90) -> list:
        """Fetch recent order history."""
        params = {'segment': 'EQUITY', 'page': 0, 'size': 50}
        data = self._get(f"{GROWW_ORDER_URL}/orders", params=params)
        if not data:
            return []

        orders = []
        for o in data.get('orders', data.get('orderData', [])):
            orders.append({
                'order_id': o.get('orderId', ''),
                'ticker': o.get('tradingSymbol', ''),
                'exchange': o.get('exchange', 'NSE'),
                'order_type': o.get('transactionType', ''),  # BUY/SELL
                'quantity': int(o.get('quantity', 0)),
                'price': float(o.get('price', 0)),
                'status': o.get('orderStatus', ''),
                'timestamp': o.get('orderTimestamp', ''),
                'product_type': o.get('productType', 'CNC'),
            })
        return orders

    # ── Market Data ─────────────────────────────────────────────────

    def get_stock_quote(self, ticker: str) -> dict:
        """Get live quote for an NSE/BSE stock."""
        data = self._get(f"{GROWW_STOCK_URL}/v1/accord/stock/{ticker}")
        if not data:
            return {}

        live = data.get('livePrice', data.get('live', {}))
        return {
            'ticker': ticker,
            'price': float(live.get('ltp', live.get('lastPrice', 0))),
            'open': float(live.get('open', 0)),
            'high': float(live.get('high', 0)),
            'low': float(live.get('low', 0)),
            'close': float(live.get('close', live.get('previousClose', 0))),
            'volume': int(live.get('volume', 0)),
            'change': float(live.get('change', 0)),
            'change_percent': float(live.get('pChange', 0)),
            'market_cap': live.get('marketCap', 0),
            '52w_high': float(data.get('yearHigh', data.get('high52', 0))),
            '52w_low': float(data.get('yearLow', data.get('low52', 0))),
            'pe_ratio': float(data.get('peRatio', data.get('pe', 0))),
            'sector': NSE_SECTOR_MAP.get(ticker, 'Other'),
        }

    def get_nse_indices(self) -> dict:
        """Get major NSE index values."""
        indices = {}
        for idx in ['NIFTY', 'NIFTYBANK', 'NIFTYIT', 'NIFTYPHARMA', 'NIFTYMETAL']:
            data = self._get(f"{GROWW_STOCK_URL}/v1/accord/index/{idx}")
            if data:
                indices[idx] = {
                    'value': float(data.get('ltp', data.get('lastPrice', 0))),
                    'change': float(data.get('change', 0)),
                    'change_percent': float(data.get('pChange', 0)),
                }
        return indices

    # ── Sync to DynamoDB ────────────────────────────────────────────

    def sync_to_dynamodb(self, client_id: str) -> dict:
        """
        Pull all Groww data and sync to WealthAI Copilot DynamoDB tables.
        This makes the data available to all 4 agents via their existing tools.

        Returns summary of synced data.
        """
        summary = {'client_id': client_id, 'synced_at': datetime.now().isoformat()}

        # Sync holdings to portfolios table
        holdings = self.get_holdings()
        if holdings:
            total_invested = sum(h['invested_value'] for h in holdings)
            total_current = sum(h['current_value'] for h in holdings)

            portfolio_item = {
                'client_id': client_id,
                'portfolio_type': 'groww_stocks',
                'source': 'groww',
                'currency': 'INR',
                'total_invested': Decimal(str(round(total_invested, 2))),
                'total_value': Decimal(str(round(total_current, 2))),
                'total_value_usd': Decimal(str(round(total_current * INR_TO_USD, 2))),
                'unrealized_pnl': Decimal(str(round(total_current - total_invested, 2))),
                'unrealized_pnl_percent': Decimal(str(round(
                    ((total_current - total_invested) / total_invested * 100) if total_invested > 0 else 0, 2
                ))),
                'holdings': [
                    {
                        'ticker': f"{h['ticker']}.NS",
                        'name': h['company_name'],
                        'shares': h['quantity'],
                        'avg_cost': Decimal(str(h['avg_price'])),
                        'current_price': Decimal(str(h['current_price'])),
                        'value': Decimal(str(round(h['current_value'], 2))),
                        'allocation': Decimal(str(round(
                            h['current_value'] / total_current * 100, 2
                        ))) if total_current > 0 else Decimal('0'),
                        'pnl': Decimal(str(round(h['pnl'], 2))),
                        'pnl_percent': Decimal(str(round(h['pnl_percent'], 2))),
                        'sector': h['sector'],
                        'exchange': h['exchange'],
                    }
                    for h in holdings
                ],
                'sector_allocation': self._calculate_sector_allocation(holdings, total_current),
                'last_synced': datetime.now().isoformat(),
            }

            table = self.dynamodb.Table('wealth_mgmt_portfolios')
            table.put_item(Item=portfolio_item)
            summary['stocks_synced'] = len(holdings)
            summary['stock_portfolio_value_inr'] = round(total_current, 2)

        # Sync mutual funds
        mf_holdings = self.get_mutual_funds()
        if mf_holdings:
            total_mf_invested = sum(f['invested_value'] for f in mf_holdings)
            total_mf_current = sum(f['current_value'] for f in mf_holdings)

            mf_item = {
                'client_id': client_id,
                'portfolio_type': 'groww_mutual_funds',
                'source': 'groww',
                'currency': 'INR',
                'total_invested': Decimal(str(round(total_mf_invested, 2))),
                'total_value': Decimal(str(round(total_mf_current, 2))),
                'total_value_usd': Decimal(str(round(total_mf_current * INR_TO_USD, 2))),
                'holdings': [
                    {
                        'scheme_name': f['scheme_name'],
                        'fund_house': f['fund_house'],
                        'category': f['category'],
                        'invested': Decimal(str(round(f['invested_value'], 2))),
                        'current': Decimal(str(round(f['current_value'], 2))),
                        'returns_pct': Decimal(str(round(f['returns_percent'], 2))),
                        'xirr': Decimal(str(round(f['xirr'], 2))),
                        'units': Decimal(str(round(f['units'], 4))),
                        'nav': Decimal(str(round(f['nav'], 4))),
                        'sip_active': f['sip_active'],
                        'sip_amount': Decimal(str(f['sip_amount'])),
                    }
                    for f in mf_holdings
                ],
                'last_synced': datetime.now().isoformat(),
            }

            table = self.dynamodb.Table('wealth_mgmt_portfolios')
            table.put_item(Item=mf_item)
            summary['mutual_funds_synced'] = len(mf_holdings)
            summary['mf_portfolio_value_inr'] = round(total_mf_current, 2)

        # Sync order history as transactions
        orders = self.get_order_history()
        if orders:
            txn_table = self.dynamodb.Table('wealth_mgmt_transactions')
            for o in orders:
                txn_table.put_item(Item={
                    'transaction_id': f"groww_{o['order_id']}",
                    'client_id': client_id,
                    'source': 'groww',
                    'type': o['order_type'].lower(),
                    'ticker': f"{o['ticker']}.NS",
                    'exchange': o['exchange'],
                    'shares': o['quantity'],
                    'price': Decimal(str(o['price'])),
                    'currency': 'INR',
                    'status': o['status'].lower(),
                    'timestamp': o['timestamp'],
                    'product_type': o['product_type'],
                })
            summary['orders_synced'] = len(orders)

        # Update client profile with Groww connection info
        profile_table = self.dynamodb.Table('wealth_mgmt_client_profiles')
        try:
            profile_table.update_item(
                Key={'client_id': client_id},
                UpdateExpression='SET groww_connected = :gc, groww_last_sync = :ts, market = :mkt, currency = :cur',
                ExpressionAttributeValues={
                    ':gc': True,
                    ':ts': datetime.now().isoformat(),
                    ':mkt': 'IN',
                    ':cur': 'INR',
                }
            )
        except Exception as e:
            logger.warning(f"Could not update profile: {e}")

        summary['status'] = 'success'
        return summary

    def _calculate_sector_allocation(self, holdings: list, total_value: float) -> dict:
        sectors = {}
        for h in holdings:
            sector = h['sector']
            sectors[sector] = sectors.get(sector, 0) + h['current_value']
        return {
            sector: Decimal(str(round(value / total_value * 100, 2)))
            for sector, value in sorted(sectors.items(), key=lambda x: -x[1])
        } if total_value > 0 else {}


# ── Indian Market Utilities ────────────────────────────────────────

INDIA_TAX_RATES = {
    'stcg_equity': 0.20,       # Short-term capital gains on equity (< 1 year) — 20% from FY 2024-25
    'ltcg_equity': 0.125,      # Long-term capital gains on equity (> 1 year, > 1.25L exemption) — 12.5%
    'ltcg_exemption': 125000,  # LTCG exemption limit per year (INR)
    'stcg_debt': 'slab',       # Debt funds taxed as per income slab
    'stt_delivery': 0.001,     # STT on delivery — 0.1%
    'stt_intraday': 0.00025,   # STT on intraday sell — 0.025%
    'stamp_duty': 0.00015,     # Stamp duty — 0.015%
    'gst': 0.18,               # GST on brokerage
    'sebi_charges': 0.000001,  # SEBI turnover charges
    'exchange_charges_nse': 0.0000297,
    'exchange_charges_bse': 0.0000275,
}

NIFTY50_STOCKS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'BHARTIARTL',
    'ITC', 'SBIN', 'LT', 'BAJFINANCE', 'HCLTECH', 'MARUTI', 'TATAMOTORS',
    'HINDUNILVR', 'SUNPHARMA', 'KOTAKBANK', 'AXISBANK', 'TITAN', 'ADANIENT',
    'NTPC', 'ASIANPAINT', 'POWERGRID', 'WIPRO', 'ULTRACEMCO', 'NESTLEIND',
    'JSWSTEEL', 'TATASTEEL', 'BAJAJFINSV', 'ONGC', 'DRREDDY', 'TECHM',
    'COALINDIA', 'DIVISLAB', 'CIPLA', 'SBILIFE', 'GRASIM', 'APOLLOHOSP',
    'BRITANNIA', 'HEROMOTOCO', 'EICHERMOT', 'BPCL', 'HDFCLIFE', 'TATACONSUM',
    'M_M', 'INDUSINDBK', 'BAJAJ_AUTO', 'HINDALCO', 'UPL', 'SHREECEM', 'LTIM',
]


def calculate_indian_tax_impact(holdings: list, sell_tickers: list = None) -> dict:
    """
    Calculate tax impact for selling positions under Indian tax rules.

    Args:
        holdings: List of holding dicts with 'ticker', 'quantity', 'avg_price',
                  'current_price', 'purchase_date'
        sell_tickers: Specific tickers to calculate for (None = all)

    Returns:
        Tax breakdown with STCG, LTCG, STT, and net proceeds
    """
    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    stcg_total = 0
    ltcg_total = 0
    total_stt = 0
    results = []

    for h in holdings:
        if sell_tickers and h['ticker'] not in sell_tickers:
            continue

        gains = (h['current_price'] - h['avg_price']) * h['quantity']
        sell_value = h['current_price'] * h['quantity']
        stt = sell_value * INDIA_TAX_RATES['stt_delivery']

        purchase_date = h.get('purchase_date', '')
        if isinstance(purchase_date, str) and purchase_date:
            try:
                pdate = datetime.fromisoformat(purchase_date)
                is_long_term = pdate < one_year_ago
            except ValueError:
                is_long_term = True
        else:
            is_long_term = True

        if gains > 0:
            if is_long_term:
                ltcg_total += gains
            else:
                stcg_total += gains

        total_stt += stt
        results.append({
            'ticker': h['ticker'],
            'gains_inr': round(gains, 2),
            'type': 'LTCG' if is_long_term else 'STCG',
            'sell_value_inr': round(sell_value, 2),
            'stt': round(stt, 2),
        })

    ltcg_taxable = max(0, ltcg_total - INDIA_TAX_RATES['ltcg_exemption'])
    ltcg_tax = ltcg_taxable * INDIA_TAX_RATES['ltcg_equity']
    stcg_tax = max(0, stcg_total) * INDIA_TAX_RATES['stcg_equity']

    return {
        'stcg_gains': round(stcg_total, 2),
        'stcg_tax': round(stcg_tax, 2),
        'stcg_rate': f"{INDIA_TAX_RATES['stcg_equity'] * 100}%",
        'ltcg_gains': round(ltcg_total, 2),
        'ltcg_exemption_used': round(min(ltcg_total, INDIA_TAX_RATES['ltcg_exemption']), 2),
        'ltcg_taxable': round(ltcg_taxable, 2),
        'ltcg_tax': round(ltcg_tax, 2),
        'ltcg_rate': f"{INDIA_TAX_RATES['ltcg_equity'] * 100}%",
        'total_stt': round(total_stt, 2),
        'total_tax': round(stcg_tax + ltcg_tax, 2),
        'effective_tax_rate': round(
            (stcg_tax + ltcg_tax) / (stcg_total + ltcg_total) * 100, 2
        ) if (stcg_total + ltcg_total) > 0 else 0,
        'per_stock': results,
        'note': 'FY 2024-25 rates. STCG@20%, LTCG@12.5% above 1.25L exemption.',
    }


def get_indian_market_hours() -> dict:
    """Check if Indian markets are open."""
    from datetime import timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)

    is_weekday = now_ist.weekday() < 5
    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    pre_open = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)

    is_open = is_weekday and market_open <= now_ist <= market_close

    return {
        'ist_time': now_ist.strftime('%Y-%m-%d %H:%M:%S IST'),
        'market_open': is_open,
        'session': 'pre-open' if (is_weekday and pre_open <= now_ist < market_open)
                   else 'trading' if is_open
                   else 'closed',
        'next_open': 'Monday 9:15 AM IST' if now_ist.weekday() >= 5
                     else 'Tomorrow 9:15 AM IST' if now_ist > market_close
                     else '9:15 AM IST',
        'exchange': 'NSE/BSE',
        'timezone': 'IST (UTC+5:30)',
    }
