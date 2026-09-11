"""
Dhan Trading Platform Connector — Read-Only Integration

Official API integration with Dhan (dhan.co) brokerage.
Supports: Equity (NSE/BSE), F&O (Futures & Options), Currency, Commodity.

Setup:
    1. Go to https://dhanhq.co/  →  Login  →  API Access
    2. Generate your access token
    3. Copy client ID and access token to .env file

Usage:
    connector = DhanConnector()
    holdings = connector.get_holdings()
    fno = connector.get_fno_positions()
    chain = connector.get_option_chain("NIFTY", "OPTIDX")
"""

import os
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import boto3
import requests

# Auto-load .env
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

DHAN_API_URL = "https://api.dhan.co/v2"

# Dhan exchange segment codes
EXCHANGE_SEGMENT = {
    'NSE_EQ': 'NSE_EQ',
    'BSE_EQ': 'BSE_EQ',
    'NSE_FNO': 'NSE_FNO',
    'BSE_FNO': 'BSE_FNO',
    'MCX_COMM': 'MCX_COMM',
    'NSE_CURRENCY': 'NSE_CURRENCY',
}

# Dhan product types
PRODUCT_TYPE = {
    'CNC': 'CNC',       # Cash & Carry (delivery)
    'INTRADAY': 'INTRADAY',
    'MARGIN': 'MARGIN',
    'CO': 'CO',          # Cover Order
    'BO': 'BO',          # Bracket Order
}

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

FNO_LOT_SIZES = {
    'NIFTY': 25, 'BANKNIFTY': 15, 'FINNIFTY': 25, 'MIDCPNIFTY': 50,
    'RELIANCE': 250, 'TCS': 150, 'HDFCBANK': 550, 'INFY': 300,
    'ICICIBANK': 700, 'SBIN': 750, 'BHARTIARTL': 475, 'ITC': 1600,
    'BAJFINANCE': 125, 'LT': 150, 'TATAMOTORS': 575, 'MARUTI': 50,
    'HCLTECH': 350, 'SUNPHARMA': 300, 'WIPRO': 1500, 'TATASTEEL': 1717,
    'AXISBANK': 600, 'KOTAKBANK': 400, 'M_M': 350, 'HINDUNILVR': 300,
}

INR_TO_USD = 0.012

INDIA_TAX_RATES = {
    'stcg_equity': 0.20,
    'ltcg_equity': 0.125,
    'ltcg_exemption': 125000,
    'stt_delivery': 0.001,
    'stt_intraday': 0.00025,
    'stt_options_sell': 0.000625,
    'stt_futures_sell': 0.000125,
    'stamp_duty': 0.00015,
    'gst': 0.18,
    'fno_tax_type': 'business_income',
    'fno_presumptive_rate': 0.06,
    'fno_audit_threshold': 100000000,
    'fno_presumptive_threshold': 20000000,
}


class DhanConnector:
    """Read-only connector to Dhan trading platform (official API)."""

    def __init__(self, access_token: str = None, client_id: str = None):
        self.client_id = client_id or os.environ.get('DHAN_CLIENT_ID', '')
        token = access_token or os.environ.get('DHAN_ACCESS_TOKEN', '')

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'access-token': token,
            'client-id': self.client_id,
        })

        self.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

    def _get(self, endpoint: str, params: dict = None) -> dict:
        try:
            resp = self.session.get(f"{DHAN_API_URL}/{endpoint}", params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Dhan API error: {e}")
            return {}

    def _post(self, endpoint: str, payload: dict = None) -> dict:
        try:
            resp = self.session.post(f"{DHAN_API_URL}/{endpoint}", json=payload or {}, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Dhan API error: {e}")
            return {}

    # ── Equity Holdings ─────────────────────────────────────────────

    def get_holdings(self) -> list:
        """Fetch all equity holdings from demat account."""
        data = self._get("holdings")
        if not data:
            return []

        holdings = []
        for h in data if isinstance(data, list) else data.get('data', []):
            ticker = h.get('tradingSymbol', '')
            qty = int(h.get('totalQty', h.get('quantity', 0)))
            avg = float(h.get('avgCostPrice', 0))
            ltp = float(h.get('lastTradedPrice', h.get('ltp', 0)))

            holdings.append({
                'ticker': ticker,
                'exchange': h.get('exchange', 'NSE'),
                'security_id': h.get('securityId', ''),
                'quantity': qty,
                'avg_price': avg,
                'current_price': ltp,
                'invested_value': round(qty * avg, 2),
                'current_value': round(qty * ltp, 2),
                'pnl': round(qty * (ltp - avg), 2),
                'pnl_percent': round(((ltp - avg) / avg) * 100, 2) if avg > 0 else 0,
                'sector': NSE_SECTOR_MAP.get(ticker, 'Other'),
                'isin': h.get('isin', ''),
            })

        return holdings

    # ── Positions (Equity + F&O) ────────────────────────────────────

    def get_positions(self) -> list:
        """Fetch all open positions (equity intraday + F&O)."""
        data = self._get("positions")
        if not data:
            return []

        positions = []
        for p in data if isinstance(data, list) else data.get('data', []):
            positions.append({
                'symbol': p.get('tradingSymbol', ''),
                'security_id': p.get('securityId', ''),
                'exchange_segment': p.get('exchangeSegment', ''),
                'product_type': p.get('productType', ''),
                'position_type': p.get('positionType', ''),
                'quantity': int(p.get('netQty', p.get('quantity', 0))),
                'buy_qty': int(p.get('buyQty', 0)),
                'sell_qty': int(p.get('sellQty', 0)),
                'buy_avg': float(p.get('buyAvg', 0)),
                'sell_avg': float(p.get('sellAvg', 0)),
                'ltp': float(p.get('lastTradedPrice', p.get('ltp', 0))),
                'realized_pnl': float(p.get('realizedProfit', 0)),
                'unrealized_pnl': float(p.get('unrealizedProfit', 0)),
                'day_buy_value': float(p.get('dayBuyValue', 0)),
                'day_sell_value': float(p.get('daySellValue', 0)),
                'multiplier': int(p.get('multiplier', 1)),
            })

        return positions

    def get_fno_positions(self) -> list:
        """Fetch only F&O positions (filtered from all positions)."""
        all_positions = self.get_positions()
        return [
            p for p in all_positions
            if p['exchange_segment'] in ('NSE_FNO', 'BSE_FNO', 'MCX_COMM')
        ]

    def get_equity_positions(self) -> list:
        """Fetch only equity intraday positions."""
        all_positions = self.get_positions()
        return [
            p for p in all_positions
            if p['exchange_segment'] in ('NSE_EQ', 'BSE_EQ')
        ]

    # ── Orders ──────────────────────────────────────────────────────

    def get_orders(self) -> list:
        """Fetch today's orders across all segments."""
        data = self._get("orders")
        if not data:
            return []

        orders = []
        for o in data if isinstance(data, list) else data.get('data', []):
            orders.append({
                'order_id': o.get('orderId', ''),
                'symbol': o.get('tradingSymbol', ''),
                'security_id': o.get('securityId', ''),
                'exchange_segment': o.get('exchangeSegment', ''),
                'transaction_type': o.get('transactionType', ''),  # BUY / SELL
                'order_type': o.get('orderType', ''),  # LIMIT / MARKET / SL / SLM
                'product_type': o.get('productType', ''),
                'quantity': int(o.get('quantity', 0)),
                'price': float(o.get('price', 0)),
                'trigger_price': float(o.get('triggerPrice', 0)),
                'traded_qty': int(o.get('tradedQuantity', 0)),
                'traded_price': float(o.get('tradedPrice', 0)),
                'status': o.get('orderStatus', ''),
                'timestamp': o.get('createTime', o.get('orderTimestamp', '')),
                'leg_name': o.get('legName', ''),
            })
        return orders

    def get_trades(self) -> list:
        """Fetch today's executed trades (fills)."""
        data = self._get("trades")
        if not data:
            return []

        trades = []
        for t in data if isinstance(data, list) else data.get('data', []):
            trades.append({
                'trade_id': t.get('tradeId', ''),
                'order_id': t.get('orderId', ''),
                'symbol': t.get('tradingSymbol', ''),
                'exchange_segment': t.get('exchangeSegment', ''),
                'transaction_type': t.get('transactionType', ''),
                'quantity': int(t.get('tradedQuantity', 0)),
                'price': float(t.get('tradedPrice', 0)),
                'timestamp': t.get('createTime', ''),
            })
        return trades

    # ── Option Chain ────────────────────────────────────────────────

    def get_option_chain(self, symbol: str, exchange_segment: str = "NSE_FNO",
                         expiry: str = None) -> dict:
        """
        Fetch option chain for an index or stock.

        Args:
            symbol: Underlying symbol (NIFTY, BANKNIFTY, RELIANCE, etc.)
            exchange_segment: NSE_FNO (default) or BSE_FNO
            expiry: Expiry date (YYYY-MM-DD). None = nearest.
        """
        payload = {
            "UnderlyingScrip": symbol,
            "ExchangeSegment": exchange_segment,
        }
        if expiry:
            payload["Expiry"] = expiry

        data = self._post("optionchain", payload)
        if not data:
            return {}

        chain = data.get('data', data)
        strikes = []

        for item in chain if isinstance(chain, list) else chain.get('optionChain', []):
            ce = item.get('ce', item.get('callOption', {}))
            pe = item.get('pe', item.get('putOption', {}))
            strike_price = float(item.get('strikePrice', 0))

            strikes.append({
                'strike_price': strike_price,
                'ce_ltp': float(ce.get('lastTradedPrice', ce.get('ltp', 0))),
                'ce_oi': int(ce.get('openInterest', ce.get('oi', 0))),
                'ce_oi_change': int(ce.get('oiDayChange', ce.get('changeinOpenInterest', 0))),
                'ce_volume': int(ce.get('volume', 0)),
                'ce_iv': float(ce.get('impliedVolatility', ce.get('iv', 0))),
                'ce_bid': float(ce.get('bestBidPrice', 0)),
                'ce_ask': float(ce.get('bestAskPrice', 0)),
                'ce_security_id': ce.get('securityId', ''),
                'pe_ltp': float(pe.get('lastTradedPrice', pe.get('ltp', 0))),
                'pe_oi': int(pe.get('openInterest', pe.get('oi', 0))),
                'pe_oi_change': int(pe.get('oiDayChange', pe.get('changeinOpenInterest', 0))),
                'pe_volume': int(pe.get('volume', 0)),
                'pe_iv': float(pe.get('impliedVolatility', pe.get('iv', 0))),
                'pe_bid': float(pe.get('bestBidPrice', 0)),
                'pe_ask': float(pe.get('bestAskPrice', 0)),
                'pe_security_id': pe.get('securityId', ''),
            })

        underlying_price = float(data.get('underlyingValue', data.get('spotPrice', 0)))
        lot_size = FNO_LOT_SIZES.get(symbol, 0)

        total_ce_oi = sum(s['ce_oi'] for s in strikes)
        total_pe_oi = sum(s['pe_oi'] for s in strikes)
        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0

        max_ce_oi = max(strikes, key=lambda s: s['ce_oi']) if strikes else {}
        max_pe_oi = max(strikes, key=lambda s: s['pe_oi']) if strikes else {}

        return {
            'symbol': symbol,
            'underlying_price': underlying_price,
            'lot_size': lot_size,
            'lot_value': round(underlying_price * lot_size, 2),
            'expiry': expiry or data.get('expiryDate', ''),
            'total_ce_oi': total_ce_oi,
            'total_pe_oi': total_pe_oi,
            'pcr': pcr,
            'pcr_interpretation': 'Bullish' if pcr > 1.2 else 'Bearish' if pcr < 0.8 else 'Neutral',
            'max_ce_oi_strike': max_ce_oi.get('strike_price', 0),
            'max_pe_oi_strike': max_pe_oi.get('strike_price', 0),
            'resistance': max_ce_oi.get('strike_price', 0),
            'support': max_pe_oi.get('strike_price', 0),
            'strikes': strikes,
            'strike_count': len(strikes),
        }

    # ── Market Quotes ───────────────────────────────────────────────

    def get_ltp(self, securities: list) -> dict:
        """
        Get last traded price for one or more securities.

        Args:
            securities: List of dicts with 'exchangeSegment' and 'securityId'
                        e.g. [{"exchangeSegment": "NSE_EQ", "securityId": "1333"}]
        """
        data = self._post("marketfeed/ltp", {"data": securities})
        if not data:
            return {}
        return data

    def get_market_quote(self, securities: list) -> dict:
        """
        Get full market quote (OHLC, volume, OI) for securities.

        Args:
            securities: List of dicts with 'exchangeSegment' and 'securityId'
        """
        data = self._post("marketfeed/quote", {"data": securities})
        if not data:
            return {}
        return data

    # ── Fund / Margin ───────────────────────────────────────────────

    def get_fund_limits(self) -> dict:
        """Fetch available funds and margin details."""
        data = self._get("fundlimit")
        if not data:
            return {}

        return {
            'available_balance': float(data.get('availabelBalance', data.get('sodLimit', 0))),
            'utilized_amount': float(data.get('utilizedAmount', 0)),
            'collateral': float(data.get('collateralAmount', 0)),
            'total_margin': float(data.get('availabelBalance', 0)) + float(data.get('collateralAmount', 0)),
            'blocked_margin': float(data.get('blockedPayoutAmount', 0)),
            'withdrawal_available': float(data.get('withdrawableBalance', 0)),
        }

    # ── Expiry List ─────────────────────────────────────────────────

    def get_expiry_list(self, symbol: str, exchange_segment: str = "NSE_FNO") -> list:
        """Fetch available expiry dates for F&O contracts."""
        payload = {
            "UnderlyingScrip": symbol,
            "ExchangeSegment": exchange_segment,
        }
        data = self._post("optionchain/expirylist", payload)
        if not data:
            return []

        return data.get('data', data.get('expiryList', []))

    # ── Sync to DynamoDB ────────────────────────────────────────────

    def sync_to_dynamodb(self, client_id: str) -> dict:
        """
        Pull all Dhan data and sync to WealthAI DynamoDB tables.
        Syncs: equity holdings, F&O positions, orders, fund limits.
        """
        summary = {'client_id': client_id, 'synced_at': datetime.now().isoformat(), 'broker': 'dhan'}

        # Sync equity holdings
        holdings = self.get_holdings()
        if holdings:
            total_invested = sum(h['invested_value'] for h in holdings)
            total_current = sum(h['current_value'] for h in holdings)

            portfolio_item = {
                'client_id': client_id,
                'portfolio_id': 'dhan_equity',
                'portfolio_type': 'dhan_equity',
                'source': 'dhan',
                'currency': 'INR',
                'total_invested': Decimal(str(round(total_invested, 2))),
                'total_value': Decimal(str(round(total_current, 2))),
                'total_value_usd': Decimal(str(round(total_current * INR_TO_USD, 2))),
                'unrealized_pnl': Decimal(str(round(total_current - total_invested, 2))),
                'holdings': [
                    {
                        'ticker': h['ticker'],
                        'shares': h['quantity'],
                        'avg_cost': Decimal(str(h['avg_price'])),
                        'current_price': Decimal(str(h['current_price'])),
                        'value': Decimal(str(h['current_value'])),
                        'pnl': Decimal(str(h['pnl'])),
                        'sector': h['sector'],
                        'exchange': h['exchange'],
                        'security_id': h['security_id'],
                    }
                    for h in holdings
                ],
                'sector_allocation': self._calculate_sector_allocation(holdings, total_current),
                'last_synced': datetime.now().isoformat(),
            }

            table = self.dynamodb.Table('wealth_mgmt_portfolios')
            table.put_item(Item=portfolio_item)
            summary['equity_synced'] = len(holdings)
            summary['equity_value_inr'] = round(total_current, 2)

        # Sync F&O positions
        fno_positions = self.get_fno_positions()
        if fno_positions:
            total_fno_pnl = sum(p['unrealized_pnl'] + p['realized_pnl'] for p in fno_positions)

            fno_item = {
                'client_id': client_id,
                'portfolio_id': 'dhan_fno',
                'portfolio_type': 'dhan_fno',
                'source': 'dhan',
                'currency': 'INR',
                'positions': [
                    {
                        'symbol': p['symbol'],
                        'exchange_segment': p['exchange_segment'],
                        'product_type': p['product_type'],
                        'quantity': p['quantity'],
                        'buy_avg': Decimal(str(p['buy_avg'])),
                        'sell_avg': Decimal(str(p['sell_avg'])),
                        'ltp': Decimal(str(p['ltp'])),
                        'realized_pnl': Decimal(str(round(p['realized_pnl'], 2))),
                        'unrealized_pnl': Decimal(str(round(p['unrealized_pnl'], 2))),
                    }
                    for p in fno_positions
                ],
                'total_pnl': Decimal(str(round(total_fno_pnl, 2))),
                'open_positions': len(fno_positions),
                'last_synced': datetime.now().isoformat(),
            }

            table = self.dynamodb.Table('wealth_mgmt_portfolios')
            table.put_item(Item=fno_item)
            summary['fno_positions_synced'] = len(fno_positions)
            summary['fno_pnl_inr'] = round(total_fno_pnl, 2)

        # Sync fund limits
        funds = self.get_fund_limits()
        if funds:
            summary['available_margin'] = funds.get('available_balance', 0)
            summary['total_margin'] = funds.get('total_margin', 0)

        # Update client profile
        profile_table = self.dynamodb.Table('wealth_mgmt_client_profiles')
        try:
            profile_table.update_item(
                Key={'client_id': client_id},
                UpdateExpression='SET dhan_connected = :dc, dhan_last_sync = :ts, market = :mkt, currency = :cur, broker = :br',
                ExpressionAttributeValues={
                    ':dc': True,
                    ':ts': datetime.now().isoformat(),
                    ':mkt': 'IN',
                    ':cur': 'INR',
                    ':br': 'dhan',
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


# ── F&O Analytics ───────────────────────────────────────────────────

def calculate_fno_turnover(trades: list) -> dict:
    """
    Calculate F&O turnover for tax/audit purposes.

    Turnover rules (ICAI):
    - Futures: absolute(sell_value - buy_value) per trade
    - Options: premium received/paid is the turnover
    """
    futures_turnover = 0
    options_turnover = 0
    futures_pnl = 0
    options_pnl = 0

    for t in trades:
        segment = t.get('exchange_segment', '')
        if 'FUT' in t.get('symbol', '') or 'FUT' in segment:
            diff = abs(t.get('day_sell_value', 0) - t.get('day_buy_value', 0))
            futures_turnover += diff
            futures_pnl += t.get('realized_pnl', 0) + t.get('unrealized_pnl', 0)
        else:
            premium = abs(t.get('day_sell_value', 0))
            options_turnover += premium
            options_pnl += t.get('realized_pnl', 0) + t.get('unrealized_pnl', 0)

    total_turnover = futures_turnover + options_turnover
    total_pnl = futures_pnl + options_pnl

    audit_required = total_turnover > INDIA_TAX_RATES['fno_audit_threshold']
    presumptive_eligible = total_turnover <= INDIA_TAX_RATES['fno_presumptive_threshold']

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
        'audit_note': 'Tax audit required under Section 44AB' if audit_required else 'No audit required',
        'presumptive_eligible': presumptive_eligible,
        'presumptive_income_44AD': round(total_turnover * INDIA_TAX_RATES['fno_presumptive_rate'], 2) if presumptive_eligible else None,
        'stt_futures': round(futures_turnover * INDIA_TAX_RATES['stt_futures_sell'], 2),
        'stt_options': round(options_turnover * INDIA_TAX_RATES['stt_options_sell'], 2),
        'note': 'F&O is business income under Section 43(5). Losses carry forward 8 years against business income only.',
    }


def calculate_option_greeks(spot: float, strike: float, expiry_days: int,
                            iv: float, option_type: str = 'CE',
                            risk_free_rate: float = 0.065) -> dict:
    """
    Calculate option Greeks using Black-Scholes.

    Args:
        spot: Underlying price
        strike: Strike price
        expiry_days: Days to expiry
        iv: Implied volatility (decimal, e.g. 0.15 for 15%)
        option_type: 'CE' (call) or 'PE' (put)
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
        'iv_percent': round(iv * 100, 2),
        'days_to_expiry': expiry_days,
        'moneyness': 'ITM' if (option_type == 'CE' and spot > strike) or (option_type == 'PE' and spot < strike)
                     else 'ATM' if abs(spot - strike) / spot < 0.01
                     else 'OTM',
        'interpretation': {
            'delta': f"₹{abs(delta):.2f} move per ₹1 underlying move",
            'gamma': f"Delta changes {gamma:.4f} per ₹1 move",
            'theta': f"Loses ₹{abs(theta):.2f}/day from time decay",
            'vega': f"₹{vega:.2f} move per 1% IV change",
        },
    }


def analyze_fno_strategy(positions: list, underlying_price: float) -> dict:
    """
    Analyze F&O strategy from open positions.

    Detects: Straddle, Strangle, Bull/Bear Spread, Iron Condor,
    Covered Call, Protective Put, Naked positions.
    """
    if not positions:
        return {'strategy': 'No positions', 'positions': []}

    calls = [p for p in positions if 'CE' in p.get('symbol', '') or p.get('option_type') == 'CE']
    puts = [p for p in positions if 'PE' in p.get('symbol', '') or p.get('option_type') == 'PE']
    futures = [p for p in positions if 'FUT' in p.get('symbol', '')]

    strategy = 'Custom'
    max_profit = None
    max_loss = None
    breakevens = []

    if len(calls) == 1 and len(puts) == 1 and not futures:
        ce = calls[0]
        pe = puts[0]
        ce_strike = float(ce.get('strike_price', 0))
        pe_strike = float(pe.get('strike_price', 0))
        ce_qty = ce.get('quantity', 0)
        pe_qty = pe.get('quantity', 0)

        if abs(ce_strike - pe_strike) < 1:
            if ce_qty > 0 and pe_qty > 0:
                strategy = 'Long Straddle'
                total_premium = abs(ce.get('buy_avg', 0)) + abs(pe.get('buy_avg', 0))
                breakevens = [ce_strike - total_premium, ce_strike + total_premium]
                max_loss = total_premium * abs(ce_qty)
            elif ce_qty < 0 and pe_qty < 0:
                strategy = 'Short Straddle'
                total_premium = abs(ce.get('sell_avg', ce.get('buy_avg', 0))) + abs(pe.get('sell_avg', pe.get('buy_avg', 0)))
                breakevens = [ce_strike - total_premium, ce_strike + total_premium]
                max_profit = total_premium * abs(ce_qty)
        elif ce_strike > pe_strike:
            if ce_qty > 0 and pe_qty > 0:
                strategy = 'Long Strangle'
            elif ce_qty < 0 and pe_qty < 0:
                strategy = 'Short Strangle'

    elif len(calls) == 2 and not puts and not futures:
        strikes = sorted([float(c.get('strike_price', 0)) for c in calls])
        qtys = [c.get('quantity', 0) for c in calls]
        if qtys[0] > 0 and qtys[1] < 0:
            strategy = 'Bull Call Spread'
        elif qtys[0] < 0 and qtys[1] > 0:
            strategy = 'Bear Call Spread'

    elif len(puts) == 2 and not calls and not futures:
        strikes = sorted([float(p.get('strike_price', 0)) for p in puts])
        qtys = [p.get('quantity', 0) for p in puts]
        if qtys[0] < 0 and qtys[1] > 0:
            strategy = 'Bull Put Spread'
        elif qtys[0] > 0 and qtys[1] < 0:
            strategy = 'Bear Put Spread'

    elif len(calls) == 2 and len(puts) == 2 and not futures:
        strategy = 'Iron Condor' if all(
            p.get('quantity', 0) != 0 for p in calls + puts
        ) else 'Custom Multi-Leg'

    elif futures and (calls or puts):
        if futures[0].get('quantity', 0) > 0 and calls and calls[0].get('quantity', 0) < 0:
            strategy = 'Covered Call (Futures)'
        elif futures[0].get('quantity', 0) > 0 and puts and puts[0].get('quantity', 0) > 0:
            strategy = 'Protective Put (Futures)'

    elif len(futures) == 1 and not calls and not puts:
        strategy = 'Long Futures' if futures[0].get('quantity', 0) > 0 else 'Short Futures'

    total_pnl = sum(p.get('unrealized_pnl', 0) + p.get('realized_pnl', 0) for p in positions)

    return {
        'strategy': strategy,
        'underlying_price': underlying_price,
        'total_positions': len(positions),
        'futures': len(futures),
        'calls': len(calls),
        'puts': len(puts),
        'total_pnl': round(total_pnl, 2),
        'max_profit': round(max_profit, 2) if max_profit else 'Unlimited' if strategy.startswith('Long') else 'N/A',
        'max_loss': round(max_loss, 2) if max_loss else 'Unlimited' if strategy.startswith('Short') else 'N/A',
        'breakevens': [round(b, 2) for b in breakevens] if breakevens else [],
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
        'fno_segment': 'NSE F&O / MCX',
        'timezone': 'IST (UTC+5:30)',
    }
