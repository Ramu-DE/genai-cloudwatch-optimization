"""
Groww Portfolio Connector — Read-Only Integration

Connects to Groww (Indian brokerage) to fetch real portfolio data.
Supports: Stocks (NSE/BSE), Mutual Funds, F&O (Futures & Options).

Usage:
    connector = GrowwConnector(auth_token="...")
    holdings = connector.get_holdings()
    mf = connector.get_mutual_funds()
    fno = connector.get_fno_positions()
    chain = connector.get_option_chain("NIFTY")

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
from pathlib import Path

import boto3
import requests

# Auto-load .env file if present
def _load_env():
    for env_path in [
        Path(__file__).parent / '.env',
        Path(__file__).parent.parent / '.env',
        Path.home() / '.wealthai' / '.env',
    ]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, val = line.split('=', 1)
                        os.environ.setdefault(key.strip(), val.strip())
            break

_load_env()

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')

GROWW_BASE_URL = "https://groww.in/v1/api"
GROWW_STOCK_URL = f"{GROWW_BASE_URL}/stocks_data"
GROWW_MF_URL = f"{GROWW_BASE_URL}/v1/mutual-fund"
GROWW_ORDER_URL = f"{GROWW_BASE_URL}/order"
GROWW_HOLDING_URL = f"{GROWW_BASE_URL}/v2/user/stocks/holdings"
GROWW_POSITIONS_URL = f"{GROWW_BASE_URL}/v2/user/stocks/positions"
GROWW_FNO_POSITIONS_URL = f"{GROWW_BASE_URL}/v1/user/derivatives/positions"
GROWW_FNO_ORDERS_URL = f"{GROWW_BASE_URL}/v1/user/derivatives/orders"
GROWW_OPTION_CHAIN_URL = f"{GROWW_BASE_URL}/v1/api/option_chain_data"
GROWW_FUTURES_URL = f"{GROWW_BASE_URL}/v1/api/futures_data"

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

FNO_LOT_SIZES = {
    'NIFTY': 25, 'BANKNIFTY': 15, 'FINNIFTY': 25, 'MIDCPNIFTY': 50,
    'RELIANCE': 250, 'TCS': 150, 'HDFCBANK': 550, 'INFY': 300,
    'ICICIBANK': 700, 'SBIN': 750, 'BHARTIARTL': 475, 'ITC': 1600,
    'BAJFINANCE': 125, 'LT': 150, 'TATAMOTORS': 575, 'MARUTI': 50,
    'HCLTECH': 350, 'SUNPHARMA': 300, 'WIPRO': 1500, 'TATASTEEL': 1717,
    'AXISBANK': 600, 'KOTAKBANK': 400, 'M_M': 350, 'HINDUNILVR': 300,
    'ADANIENT': 250, 'TITAN': 375, 'NTPC': 2800, 'POWERGRID': 2700,
}


class GrowwConnector:
    """Read-only connector to Groww brokerage platform."""

    def __init__(self, auth_token: str = None, access_token: str = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

        token = auth_token or os.environ.get('GROWW_AUTH_TOKEN', '')
        if token:
            if token.startswith('Bearer '):
                self.session.headers['Authorization'] = token
            else:
                self.session.headers['Authorization'] = f'Bearer {token}'

        acc_token = access_token or os.environ.get('GROWW_ACCESS_TOKEN', '')
        if acc_token:
            self.session.headers['x-access-token'] = acc_token

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

    # ── F&O (Futures & Options) ────────────────────────────────────

    def get_fno_positions(self) -> list:
        """Fetch open F&O positions (futures and options)."""
        data = self._get(GROWW_FNO_POSITIONS_URL)
        if not data:
            return []

        positions = []
        for p in data.get('positionData', data.get('positions', data.get('data', []))):
            symbol = p.get('tradingSymbol', p.get('symbol', ''))
            positions.append({
                'symbol': symbol,
                'underlying': p.get('underlying', symbol.split('-')[0] if '-' in symbol else symbol),
                'exchange': p.get('exchange', 'NFO'),
                'instrument_type': p.get('instrumentType', self._detect_instrument(symbol)),
                'option_type': p.get('optionType', ''),  # CE / PE
                'strike_price': float(p.get('strikePrice', 0)),
                'expiry': p.get('expiry', p.get('expiryDate', '')),
                'lot_size': int(p.get('lotSize', p.get('marketLot', 0))),
                'quantity': int(p.get('quantity', p.get('netQuantity', 0))),
                'buy_price': float(p.get('buyPrice', p.get('averagePrice', 0))),
                'current_price': float(p.get('lastTradedPrice', p.get('ltp', 0))),
                'pnl': float(p.get('pnl', p.get('unrealisedPnl', 0))),
                'buy_value': float(p.get('buyValue', 0)),
                'current_value': float(p.get('currentValue', 0)),
                'product_type': p.get('productType', 'NRML'),  # NRML / MIS
            })
        return positions

    def get_fno_orders(self, days: int = 30) -> list:
        """Fetch F&O order history."""
        params = {'segment': 'FNO', 'page': 0, 'size': 50}
        data = self._get(GROWW_FNO_ORDERS_URL, params=params)
        if not data:
            return []

        orders = []
        for o in data.get('orders', data.get('orderData', data.get('data', []))):
            orders.append({
                'order_id': o.get('orderId', ''),
                'symbol': o.get('tradingSymbol', ''),
                'underlying': o.get('underlying', ''),
                'instrument_type': o.get('instrumentType', ''),
                'option_type': o.get('optionType', ''),
                'strike_price': float(o.get('strikePrice', 0)),
                'expiry': o.get('expiry', ''),
                'order_type': o.get('transactionType', ''),
                'quantity': int(o.get('quantity', 0)),
                'price': float(o.get('price', 0)),
                'status': o.get('orderStatus', ''),
                'timestamp': o.get('orderTimestamp', ''),
                'product_type': o.get('productType', 'NRML'),
            })
        return orders

    def get_option_chain(self, symbol: str, expiry: str = None) -> dict:
        """
        Fetch option chain for an index or stock.

        Args:
            symbol: Underlying symbol (e.g., NIFTY, BANKNIFTY, RELIANCE)
            expiry: Specific expiry date (YYYY-MM-DD). None = nearest expiry.
        """
        params = {'symbol': symbol}
        if expiry:
            params['expiry'] = expiry

        data = self._get(f"{GROWW_OPTION_CHAIN_URL}/{symbol}", params=params)
        if not data:
            return {}

        chain_data = data.get('optionChainData', data.get('data', data))
        strikes = []

        for strike in chain_data.get('strikes', chain_data.get('optionChain', [])):
            ce = strike.get('callOption', strike.get('CE', {}))
            pe = strike.get('putOption', strike.get('PE', {}))
            strike_price = float(strike.get('strikePrice', 0))

            strikes.append({
                'strike_price': strike_price,
                'ce_ltp': float(ce.get('lastTradedPrice', ce.get('ltp', 0))),
                'ce_oi': int(ce.get('openInterest', ce.get('oi', 0))),
                'ce_oi_change': int(ce.get('oiChange', ce.get('changeinOpenInterest', 0))),
                'ce_volume': int(ce.get('volume', ce.get('totalTradedVolume', 0))),
                'ce_iv': float(ce.get('impliedVolatility', ce.get('iv', 0))),
                'ce_bid': float(ce.get('bidPrice', ce.get('bidprice', 0))),
                'ce_ask': float(ce.get('askPrice', ce.get('askprice', 0))),
                'pe_ltp': float(pe.get('lastTradedPrice', pe.get('ltp', 0))),
                'pe_oi': int(pe.get('openInterest', pe.get('oi', 0))),
                'pe_oi_change': int(pe.get('oiChange', pe.get('changeinOpenInterest', 0))),
                'pe_volume': int(pe.get('volume', pe.get('totalTradedVolume', 0))),
                'pe_iv': float(pe.get('impliedVolatility', pe.get('iv', 0))),
                'pe_bid': float(pe.get('bidPrice', pe.get('bidprice', 0))),
                'pe_ask': float(pe.get('askPrice', pe.get('askprice', 0))),
            })

        underlying_price = float(chain_data.get('underlyingValue',
                                   chain_data.get('spotPrice', 0)))
        lot_size = FNO_LOT_SIZES.get(symbol, int(chain_data.get('lotSize', 0)))

        total_ce_oi = sum(s['ce_oi'] for s in strikes)
        total_pe_oi = sum(s['pe_oi'] for s in strikes)
        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0

        max_ce_oi_strike = max(strikes, key=lambda s: s['ce_oi'])['strike_price'] if strikes else 0
        max_pe_oi_strike = max(strikes, key=lambda s: s['pe_oi'])['strike_price'] if strikes else 0

        return {
            'symbol': symbol,
            'underlying_price': underlying_price,
            'lot_size': lot_size,
            'expiry': expiry or chain_data.get('expiryDate', chain_data.get('nearestExpiry', '')),
            'total_ce_oi': total_ce_oi,
            'total_pe_oi': total_pe_oi,
            'pcr': pcr,
            'pcr_interpretation': 'Bullish' if pcr > 1.2 else 'Bearish' if pcr < 0.8 else 'Neutral',
            'max_ce_oi_strike': max_ce_oi_strike,
            'max_pe_oi_strike': max_pe_oi_strike,
            'resistance': max_ce_oi_strike,
            'support': max_pe_oi_strike,
            'strikes': strikes,
            'strike_count': len(strikes),
        }

    def get_futures_data(self, symbol: str) -> dict:
        """Fetch futures contract data for an index or stock."""
        data = self._get(f"{GROWW_FUTURES_URL}/{symbol}")
        if not data:
            return {}

        contracts = []
        for c in data.get('futuresData', data.get('data', data.get('contracts', []))):
            contracts.append({
                'symbol': c.get('tradingSymbol', f"{symbol}FUT"),
                'expiry': c.get('expiry', c.get('expiryDate', '')),
                'ltp': float(c.get('lastTradedPrice', c.get('ltp', 0))),
                'open_interest': int(c.get('openInterest', c.get('oi', 0))),
                'oi_change': int(c.get('oiChange', 0)),
                'volume': int(c.get('volume', 0)),
                'basis': float(c.get('basis', c.get('premium', 0))),
                'basis_percent': float(c.get('basisPercent', 0)),
            })

        spot_price = float(data.get('spotPrice', data.get('underlyingValue', 0)))
        lot_size = FNO_LOT_SIZES.get(symbol, 0)

        return {
            'symbol': symbol,
            'spot_price': spot_price,
            'lot_size': lot_size,
            'lot_value': round(spot_price * lot_size, 2),
            'contracts': contracts,
        }

    def _detect_instrument(self, symbol: str) -> str:
        if 'CE' in symbol or 'PE' in symbol:
            return 'OPTION'
        if 'FUT' in symbol:
            return 'FUTURE'
        return 'UNKNOWN'

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

        # Sync F&O positions
        fno_positions = self.get_fno_positions()
        if fno_positions:
            fno_item = {
                'client_id': client_id,
                'portfolio_type': 'groww_fno',
                'source': 'groww',
                'currency': 'INR',
                'positions': [
                    {
                        'symbol': p['symbol'],
                        'underlying': p['underlying'],
                        'instrument_type': p['instrument_type'],
                        'option_type': p.get('option_type', ''),
                        'strike_price': Decimal(str(p['strike_price'])),
                        'expiry': p['expiry'],
                        'lot_size': p['lot_size'],
                        'quantity': p['quantity'],
                        'buy_price': Decimal(str(p['buy_price'])),
                        'current_price': Decimal(str(p['current_price'])),
                        'pnl': Decimal(str(round(p['pnl'], 2))),
                        'product_type': p['product_type'],
                    }
                    for p in fno_positions
                ],
                'total_pnl': Decimal(str(round(sum(p['pnl'] for p in fno_positions), 2))),
                'open_positions': len(fno_positions),
                'futures_count': sum(1 for p in fno_positions if p['instrument_type'] == 'FUTURE'),
                'options_count': sum(1 for p in fno_positions if p['instrument_type'] == 'OPTION'),
                'last_synced': datetime.now().isoformat(),
            }

            table = self.dynamodb.Table('wealth_mgmt_portfolios')
            table.put_item(Item=fno_item)
            summary['fno_positions_synced'] = len(fno_positions)
            summary['fno_pnl_inr'] = round(sum(p['pnl'] for p in fno_positions), 2)

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
    'stt_options_sell': 0.000625,  # STT on options sell — 0.0625% on premium
    'stt_futures_sell': 0.000125,  # STT on futures sell — 0.0125%
    'stamp_duty': 0.00015,     # Stamp duty — 0.015%
    'gst': 0.18,               # GST on brokerage
    'sebi_charges': 0.000001,  # SEBI turnover charges
    'exchange_charges_nse': 0.0000297,
    'exchange_charges_bse': 0.0000275,
    # F&O is business income — taxed at slab rate, NOT capital gains
    'fno_tax_type': 'business_income',
    'fno_presumptive_rate': 0.06,       # Section 44AD — 6% of turnover if < 2Cr
    'fno_audit_threshold': 100000000,   # ₹10Cr — tax audit required above this turnover
    'fno_presumptive_threshold': 20000000,  # ₹2Cr — above this, normal computation required
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


def calculate_fno_turnover(trades: list) -> dict:
    """
    Calculate F&O turnover for tax/audit purposes.

    F&O turnover rules (ICAI guidance):
    - Futures: absolute(sell_value - buy_value) per trade
    - Options: absolute premium received/paid (premium is the turnover)
    - This determines: presumptive taxation eligibility, audit requirement

    Args:
        trades: List of F&O trade dicts with 'instrument_type', 'buy_value',
                'sell_value', 'premium', 'quantity', 'lot_size'
    """
    futures_turnover = 0
    options_turnover = 0
    futures_pnl = 0
    options_pnl = 0

    for t in trades:
        if t.get('instrument_type') == 'FUTURE':
            diff = abs(t.get('sell_value', 0) - t.get('buy_value', 0))
            futures_turnover += diff
            futures_pnl += t.get('sell_value', 0) - t.get('buy_value', 0)
        else:
            premium = abs(t.get('premium', t.get('sell_value', 0)))
            options_turnover += premium
            options_pnl += t.get('pnl', 0)

    total_turnover = futures_turnover + options_turnover
    total_pnl = futures_pnl + options_pnl

    audit_required = total_turnover > INDIA_TAX_RATES['fno_audit_threshold']
    presumptive_eligible = total_turnover <= INDIA_TAX_RATES['fno_presumptive_threshold']

    presumptive_income = total_turnover * INDIA_TAX_RATES['fno_presumptive_rate']

    stt_futures = futures_turnover * INDIA_TAX_RATES['stt_futures_sell']
    stt_options = options_turnover * INDIA_TAX_RATES['stt_options_sell']

    return {
        'futures_turnover': round(futures_turnover, 2),
        'options_turnover': round(options_turnover, 2),
        'total_turnover': round(total_turnover, 2),
        'futures_pnl': round(futures_pnl, 2),
        'options_pnl': round(options_pnl, 2),
        'total_pnl': round(total_pnl, 2),
        'tax_type': 'Business Income (not Capital Gains)',
        'taxed_at': 'Income tax slab rate',
        'audit_required': audit_required,
        'audit_threshold': '₹10 Crore',
        'presumptive_eligible': presumptive_eligible,
        'presumptive_threshold': '₹2 Crore',
        'presumptive_income_44AD': round(presumptive_income, 2) if presumptive_eligible else None,
        'stt_futures': round(stt_futures, 2),
        'stt_options': round(stt_options, 2),
        'total_stt': round(stt_futures + stt_options, 2),
        'note': 'F&O income is business income under Section 43(5). '
                'Losses carry forward 8 years, set off against business income only.',
    }


def calculate_option_greeks(spot: float, strike: float, expiry_days: int,
                            iv: float, option_type: str = 'CE',
                            risk_free_rate: float = 0.065) -> dict:
    """
    Calculate option Greeks using Black-Scholes approximation.

    Args:
        spot: Current underlying price
        strike: Option strike price
        expiry_days: Days to expiry
        iv: Implied volatility (as decimal, e.g. 0.15 for 15%)
        option_type: 'CE' for call, 'PE' for put
        risk_free_rate: Risk-free rate (default 6.5% — India 10Y yield)
    """
    import math

    if expiry_days <= 0 or iv <= 0:
        return {'error': 'Invalid expiry or IV'}

    T = expiry_days / 365.0
    sqrt_T = math.sqrt(T)

    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv**2) * T) / (iv * sqrt_T)
    d2 = d1 - iv * sqrt_T

    def norm_cdf(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def norm_pdf(x):
        return math.exp(-0.5 * x**2) / math.sqrt(2 * math.pi)

    if option_type.upper() == 'CE':
        delta = round(norm_cdf(d1), 4)
        theta = round((-spot * norm_pdf(d1) * iv / (2 * sqrt_T)
                       - risk_free_rate * strike * math.exp(-risk_free_rate * T) * norm_cdf(d2)) / 365, 2)
    else:
        delta = round(norm_cdf(d1) - 1, 4)
        theta = round((-spot * norm_pdf(d1) * iv / (2 * sqrt_T)
                       + risk_free_rate * strike * math.exp(-risk_free_rate * T) * norm_cdf(-d2)) / 365, 2)

    gamma = round(norm_pdf(d1) / (spot * iv * sqrt_T), 6)
    vega = round(spot * norm_pdf(d1) * sqrt_T / 100, 2)

    return {
        'delta': delta,
        'gamma': gamma,
        'theta': theta,
        'vega': vega,
        'iv': round(iv * 100, 2),
        'days_to_expiry': expiry_days,
        'interpretation': {
            'delta': f"Option moves ₹{abs(delta):.2f} for every ₹1 move in underlying",
            'gamma': f"Delta changes by {gamma:.4f} for every ₹1 move",
            'theta': f"Option loses ₹{abs(theta):.2f} per day from time decay",
            'vega': f"Option moves ₹{vega:.2f} for every 1% change in IV",
        },
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
