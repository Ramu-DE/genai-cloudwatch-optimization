"""
Market Data Lambda — Fast API for real-time Indian market data.

Serves index quotes, option chains, Dhan holdings, fund limits,
financial news, and a combined dashboard view. No LLM inference —
returns structured JSON for the trading dashboard UI.
"""

import json
import os
import math
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS, GET',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Content-Type': 'application/json',
}

IST = timezone(timedelta(hours=5, minutes=30))

DHAN_API_BASE = 'https://api.dhan.co/v2'

FNO_LOT_SIZES = {
    'NIFTY': 25, 'BANKNIFTY': 15, 'FINNIFTY': 25, 'MIDCPNIFTY': 50,
    'RELIANCE': 250, 'TCS': 150, 'HDFCBANK': 550, 'INFY': 300,
    'ICICIBANK': 700, 'SBIN': 750, 'BHARTIARTL': 475, 'ITC': 1600,
    'BAJFINANCE': 125, 'LT': 150, 'TATAMOTORS': 575, 'MARUTI': 50,
    'HCLTECH': 350, 'SUNPHARMA': 300, 'WIPRO': 1500, 'TATASTEEL': 1717,
    'AXISBANK': 600, 'KOTAKBANK': 400, 'M_M': 350, 'HINDUNILVR': 300,
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

KEY_INDEX_NAMES = [
    'NIFTY 50', 'NIFTY BANK', 'INDIA VIX', 'NIFTY FIN SERVICE',
    'NIFTY IT', 'NIFTY AUTO', 'NIFTY PHARMA', 'NIFTY METAL',
    'NIFTY FMCG', 'NIFTY MIDCAP 50', 'NIFTY NEXT 50', 'NIFTY ENERGY',
    'NIFTY REALTY', 'NIFTY INFRA', 'NIFTY PSE',
]

NEWS_FEEDS = [
    {
        'url': 'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
        'source': 'Economic Times',
    },
]


# ── Helpers ──────────────────────────────────────────────────────────

def _respond(status, body):
    return {
        'statusCode': status,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=str),
    }


def _nse_opener():
    """Build a urllib opener with cookie support for NSE session."""
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    opener.addheaders = [('User-Agent', ua), ('Accept', '*/*')]
    try:
        opener.open('https://www.nseindia.com', timeout=8)
    except Exception:
        pass
    return opener


def _nse_get(opener, url, timeout=10):
    """Fetch JSON from NSE API using an opener that already has cookies."""
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.nseindia.com/',
    })
    try:
        resp = opener.open(req, timeout=timeout)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.warning(f'NSE API error for {url}: {e}')
        return None


def _dhan_get(endpoint):
    """GET from Dhan Trading API."""
    token = os.environ.get('DHAN_ACCESS_TOKEN', '')
    client_id = os.environ.get('DHAN_CLIENT_ID', '')
    if not token or not client_id:
        return None

    url = f'{DHAN_API_BASE}/{endpoint}'
    req = Request(url, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'access-token': token,
        'client-id': client_id,
    })
    try:
        resp = urlopen(req, timeout=10)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.warning(f'Dhan API error for {endpoint}: {e}')
        return None


def _market_hours():
    now = datetime.now(IST)
    weekday = now.weekday() < 5
    mkt_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    mkt_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    pre_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    is_open = weekday and mkt_open <= now <= mkt_close

    return {
        'ist_time': now.strftime('%Y-%m-%d %H:%M:%S IST'),
        'market_open': is_open,
        'session': (
            'pre-open' if (weekday and pre_open <= now < mkt_open)
            else 'trading' if is_open
            else 'closed'
        ),
        'next_open': (
            'Monday 9:15 AM IST' if now.weekday() >= 5
            else 'Tomorrow 9:15 AM IST' if now > mkt_close
            else '9:15 AM IST'
        ),
    }


# ── Greeks (Black-Scholes, inline) ──────────────────────────────────

def calculate_option_greeks(spot, strike, expiry_days, iv,
                            option_type='CE', risk_free_rate=0.065):
    if expiry_days <= 0 or iv <= 0:
        return {'error': 'Invalid expiry or IV'}

    T = expiry_days / 365.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv ** 2) * T) / (iv * sqrt_T)
    d2 = d1 - iv * sqrt_T

    def ncdf(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def npdf(x):
        return math.exp(-0.5 * x ** 2) / math.sqrt(2 * math.pi)

    if option_type.upper() == 'CE':
        delta = round(ncdf(d1), 4)
        theta = round((-spot * npdf(d1) * iv / (2 * sqrt_T)
                       - risk_free_rate * strike * math.exp(-risk_free_rate * T) * ncdf(d2)) / 365, 2)
    else:
        delta = round(ncdf(d1) - 1, 4)
        theta = round((-spot * npdf(d1) * iv / (2 * sqrt_T)
                       + risk_free_rate * strike * math.exp(-risk_free_rate * T) * ncdf(-d2)) / 365, 2)

    gamma = round(npdf(d1) / (spot * iv * sqrt_T), 6)
    vega = round(spot * npdf(d1) * sqrt_T / 100, 2)

    moneyness = (
        'ITM' if (option_type.upper() == 'CE' and spot > strike) or
                 (option_type.upper() == 'PE' and spot < strike)
        else 'ATM' if abs(spot - strike) / spot < 0.01
        else 'OTM'
    )

    return {
        'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega,
        'iv_percent': round(iv * 100, 2),
        'days_to_expiry': expiry_days,
        'moneyness': moneyness,
    }


# ── Action handlers ──────────────────────────────────────────────────

def action_indices():
    """Fetch NSE index data."""
    opener = _nse_opener()
    data = _nse_get(opener, 'https://www.nseindia.com/api/allIndices')
    if not data:
        return {'error': 'Could not fetch NSE indices'}

    indices = {}
    for idx in data.get('data', []):
        name = idx.get('index', '')
        if name in KEY_INDEX_NAMES:
            indices[name] = {
                'last': float(idx.get('last', 0)),
                'change': float(idx.get('percentChange', 0)),
                'open': float(idx.get('open', 0)),
                'high': float(idx.get('high', 0)),
                'low': float(idx.get('low', 0)),
                'prev_close': float(idx.get('previousClose', 0)),
            }

    nifty = indices.get('NIFTY 50', {})
    vix = indices.get('INDIA VIX', {})
    vix_val = vix.get('last', 0)

    return {
        'indices': indices,
        'nifty_spot': nifty.get('last', 0),
        'nifty_change': nifty.get('change', 0),
        'banknifty_spot': indices.get('NIFTY BANK', {}).get('last', 0),
        'banknifty_change': indices.get('NIFTY BANK', {}).get('change', 0),
        'vix': vix_val,
        'vix_change': vix.get('change', 0),
        'vix_signal': (
            'LOW — Sell strategies favorable (Iron Condor, Short Strangle)'
            if vix_val < 14
            else 'MODERATE — Neutral strategies'
            if vix_val < 18
            else 'HIGH — Buy strategies / hedging recommended'
        ),
        'market': _market_hours(),
    }


def action_option_chain(symbol='NIFTY'):
    """Fetch option chain from NSE."""
    symbol = symbol.upper()
    opener = _nse_opener()

    url = f'https://www.nseindia.com/api/option-chain-indices?symbol={symbol}'
    data = _nse_get(opener, url)

    if not data or 'records' not in data:
        idx_data = _nse_get(opener, 'https://www.nseindia.com/api/allIndices')
        spot = 0
        if idx_data:
            for idx in idx_data.get('data', []):
                if symbol in idx.get('index', ''):
                    spot = float(idx.get('last', 0))
                    break

        return {
            'symbol': symbol,
            'underlying_price': spot,
            'lot_size': FNO_LOT_SIZES.get(symbol, 0),
            'available': False,
            'message': 'Option chain not available (NSE API may be restricted outside market hours)',
            'strikes': [],
        }

    records = data['records']
    underlying = float(records.get('underlyingValue', 0))
    expiries = records.get('expiryDates', [])
    oc_data = records.get('data', [])
    nearest_exp = expiries[0] if expiries else ''
    nearest = [d for d in oc_data if d.get('expiryDate') == nearest_exp]

    strikes = []
    for item in nearest:
        ce = item.get('CE', {})
        pe = item.get('PE', {})
        strikes.append({
            'strike_price': float(item.get('strikePrice', 0)),
            'ce_ltp': float(ce.get('lastPrice', 0)),
            'ce_oi': int(ce.get('openInterest', 0)),
            'ce_oi_change': int(ce.get('changeinOpenInterest', 0)),
            'ce_volume': int(ce.get('totalTradedVolume', 0)),
            'ce_iv': float(ce.get('impliedVolatility', 0)),
            'ce_bid': float(ce.get('bidprice', 0)),
            'ce_ask': float(ce.get('askPrice', 0)),
            'pe_ltp': float(pe.get('lastPrice', 0)),
            'pe_oi': int(pe.get('openInterest', 0)),
            'pe_oi_change': int(pe.get('changeinOpenInterest', 0)),
            'pe_volume': int(pe.get('totalTradedVolume', 0)),
            'pe_iv': float(pe.get('impliedVolatility', 0)),
            'pe_bid': float(pe.get('bidprice', 0)),
            'pe_ask': float(pe.get('askPrice', 0)),
        })

    total_ce_oi = sum(s['ce_oi'] for s in strikes)
    total_pe_oi = sum(s['pe_oi'] for s in strikes)
    pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0
    max_ce = max(strikes, key=lambda s: s['ce_oi']) if strikes else {}
    max_pe = max(strikes, key=lambda s: s['pe_oi']) if strikes else {}
    lot = FNO_LOT_SIZES.get(symbol, 0)

    atm_strike = round(underlying / 50) * 50 if symbol in ('NIFTY', 'FINNIFTY') else round(underlying / 100) * 100

    atm_greeks = {}
    atm_items = [s for s in strikes if s['strike_price'] == atm_strike]
    if atm_items and nearest_exp:
        try:
            exp_date = datetime.strptime(nearest_exp, '%d-%b-%Y')
            dte = max((exp_date - datetime.now()).days, 1)
            ce_iv_dec = atm_items[0]['ce_iv'] / 100 if atm_items[0]['ce_iv'] > 0 else 0.12
            pe_iv_dec = atm_items[0]['pe_iv'] / 100 if atm_items[0]['pe_iv'] > 0 else 0.12
            atm_greeks = {
                'strike': atm_strike,
                'dte': dte,
                'ce': calculate_option_greeks(underlying, atm_strike, dte, ce_iv_dec, 'CE'),
                'pe': calculate_option_greeks(underlying, atm_strike, dte, pe_iv_dec, 'PE'),
            }
        except Exception as e:
            logger.warning(f'Greeks calc error: {e}')

    return {
        'symbol': symbol,
        'available': True,
        'underlying_price': underlying,
        'lot_size': lot,
        'lot_value': round(underlying * lot, 2),
        'expiry': nearest_exp,
        'all_expiries': expiries[:8],
        'total_ce_oi': total_ce_oi,
        'total_pe_oi': total_pe_oi,
        'pcr': pcr,
        'pcr_interpretation': 'Bullish' if pcr > 1.2 else 'Bearish' if pcr < 0.8 else 'Neutral',
        'resistance': max_ce.get('strike_price', 0),
        'support': max_pe.get('strike_price', 0),
        'atm_strike': atm_strike,
        'atm_greeks': atm_greeks,
        'strikes': strikes,
        'strike_count': len(strikes),
    }


def action_holdings():
    """Fetch Dhan equity holdings."""
    data = _dhan_get('holdings')
    if not data:
        return {'error': 'Could not fetch holdings. Check Dhan credentials.', 'holdings': []}

    raw = data if isinstance(data, list) else data.get('data', [])
    holdings = []
    for h in raw:
        ticker = h.get('tradingSymbol', '')
        qty = int(h.get('totalQty', h.get('quantity', 0)))
        avg = float(h.get('avgCostPrice', 0))
        ltp = float(h.get('lastTradedPrice', h.get('ltp', 0)))
        holdings.append({
            'ticker': ticker,
            'exchange': h.get('exchange', 'NSE'),
            'quantity': qty,
            'avg_price': avg,
            'current_price': ltp,
            'invested': round(qty * avg, 2),
            'current_value': round(qty * ltp, 2),
            'pnl': round(qty * (ltp - avg), 2),
            'pnl_pct': round(((ltp - avg) / avg) * 100, 2) if avg > 0 else 0,
            'sector': NSE_SECTOR_MAP.get(ticker, 'Other'),
        })

    total_inv = sum(h['invested'] for h in holdings)
    total_cur = sum(h['current_value'] for h in holdings)
    return {
        'count': len(holdings),
        'total_invested': round(total_inv, 2),
        'total_current': round(total_cur, 2),
        'total_pnl': round(total_cur - total_inv, 2),
        'total_pnl_pct': round((total_cur - total_inv) / total_inv * 100, 2) if total_inv > 0 else 0,
        'holdings': sorted(holdings, key=lambda h: -abs(h['current_value'])),
    }


def action_fund_limits():
    """Fetch Dhan fund/margin limits."""
    data = _dhan_get('fundlimit')
    if not data:
        return {'error': 'Could not fetch fund limits.'}

    return {
        'available_balance': float(data.get('availabelBalance', data.get('sodLimit', 0))),
        'utilized': float(data.get('utilizedAmount', 0)),
        'collateral': float(data.get('collateralAmount', 0)),
        'total_margin': float(data.get('availabelBalance', 0)) + float(data.get('collateralAmount', 0)),
        'blocked': float(data.get('blockedPayoutAmount', 0)),
        'withdrawal': float(data.get('withdrawableBalance', 0)),
    }


def action_news():
    """Fetch financial news from RSS feeds."""
    articles = []
    for feed in NEWS_FEEDS:
        try:
            req = Request(feed['url'], headers={
                'User-Agent': 'Mozilla/5.0 (compatible; WealthAI/1.0)',
            })
            resp = urlopen(req, timeout=8)
            xml_data = resp.read().decode('utf-8')
            root = ET.fromstring(xml_data)

            for item in root.iter('item'):
                title = item.findtext('title', '')
                link = item.findtext('link', '')
                pub_date = item.findtext('pubDate', '')
                desc = item.findtext('description', '')

                if title:
                    articles.append({
                        'title': title.strip(),
                        'link': link.strip(),
                        'published': pub_date.strip(),
                        'summary': desc.strip()[:200] if desc else '',
                        'source': feed['source'],
                    })

                if len(articles) >= 20:
                    break
        except Exception as e:
            logger.warning(f'News feed error ({feed["source"]}): {e}')

    return {
        'count': len(articles),
        'articles': articles[:20],
        'fetched_at': datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'),
    }


def action_positions():
    """Fetch Dhan open positions (equity + F&O)."""
    data = _dhan_get('positions')
    if not data:
        return {'positions': [], 'fno_positions': [], 'equity_positions': []}

    raw = data if isinstance(data, list) else data.get('data', [])
    positions = []
    for p in raw:
        positions.append({
            'symbol': p.get('tradingSymbol', ''),
            'exchange_segment': p.get('exchangeSegment', ''),
            'product_type': p.get('productType', ''),
            'quantity': int(p.get('netQty', p.get('quantity', 0))),
            'buy_avg': float(p.get('buyAvg', 0)),
            'sell_avg': float(p.get('sellAvg', 0)),
            'ltp': float(p.get('lastTradedPrice', p.get('ltp', 0))),
            'realized_pnl': float(p.get('realizedProfit', 0)),
            'unrealized_pnl': float(p.get('unrealizedProfit', 0)),
        })

    fno = [p for p in positions if p['exchange_segment'] in ('NSE_FNO', 'BSE_FNO', 'MCX_COMM')]
    eq = [p for p in positions if p['exchange_segment'] in ('NSE_EQ', 'BSE_EQ')]

    return {
        'total': len(positions),
        'fno_count': len(fno),
        'equity_count': len(eq),
        'fno_pnl': round(sum(p['unrealized_pnl'] + p['realized_pnl'] for p in fno), 2),
        'positions': positions,
        'fno_positions': fno,
        'equity_positions': eq,
    }


def action_full_dashboard():
    """Combine all data sources into a single dashboard response."""
    market = _market_hours()
    result = {
        'market_status': market,
    }

    try:
        idx_result = action_indices()
        result['indices'] = idx_result.get('indices', {})
        result['nifty_spot'] = idx_result.get('nifty_spot', 0)
        result['nifty_change'] = idx_result.get('nifty_change', 0)
        result['banknifty_spot'] = idx_result.get('banknifty_spot', 0)
        result['vix'] = idx_result.get('vix', 0)
        result['vix_signal'] = idx_result.get('vix_signal', '')
    except Exception as e:
        result['indices'] = {'error': str(e)}

    try:
        result['holdings'] = action_holdings()
    except Exception as e:
        result['holdings'] = {'error': str(e)}

    try:
        result['positions'] = action_positions()
    except Exception as e:
        result['positions'] = {'error': str(e)}

    try:
        result['fund_limits'] = action_fund_limits()
    except Exception as e:
        result['fund_limits'] = {'error': str(e)}

    try:
        result['news'] = action_news()
    except Exception as e:
        result['news'] = {'error': str(e)}

    nifty_spot = result.get('nifty_spot', 0)
    if nifty_spot > 0:
        vix = result.get('vix', 12)
        atm = round(nifty_spot / 50) * 50
        result['agent_analysis'] = _generate_analysis(nifty_spot, atm, result, vix)

    return result


def _generate_analysis(spot, atm, idx_data, vix):
    """Generate agent-style F&O recommendations based on market data."""
    nifty_chg = idx_data.get('nifty_change', 0)
    bn_chg = idx_data.get('banknifty_change', 0)
    bn_spot = idx_data.get('banknifty_spot', 0)

    if nifty_chg > 0.5:
        bias = 'BULLISH'
    elif nifty_chg < -0.5:
        bias = 'BEARISH'
    else:
        bias = 'NEUTRAL'

    strategies = []

    if vix < 14:
        strategies.append({
            'name': 'Short Iron Condor',
            'bias': 'NEUTRAL',
            'confidence': 'HIGH',
            'legs': [
                {'action': 'SELL', 'strike': atm + 200, 'type': 'CE', 'lot': 25},
                {'action': 'BUY', 'strike': atm + 400, 'type': 'CE', 'lot': 25},
                {'action': 'SELL', 'strike': atm - 200, 'type': 'PE', 'lot': 25},
                {'action': 'BUY', 'strike': atm - 400, 'type': 'PE', 'lot': 25},
            ],
            'max_profit': 'Premium collected',
            'max_loss': f'₹{(200 * 25):,}/lot minus premium',
            'breakeven_upper': atm + 200,
            'breakeven_lower': atm - 200,
            'stop_loss': f'Exit if NIFTY breaks {atm - 300} or {atm + 300}',
            'rationale': f'VIX at {vix:.1f} is low — option premiums cheap to sell. Range-bound market expected.',
        })

    if bn_chg > 0 or nifty_chg > -0.3:
        strategies.append({
            'name': 'Bull Put Spread',
            'bias': 'MILDLY BULLISH',
            'confidence': 'MEDIUM',
            'legs': [
                {'action': 'SELL', 'strike': atm - 100, 'type': 'PE', 'lot': 25},
                {'action': 'BUY', 'strike': atm - 300, 'type': 'PE', 'lot': 25},
            ],
            'max_profit': 'Premium received × 25',
            'max_loss': f'₹{(200 * 25):,}/lot minus premium',
            'breakeven_lower': atm - 100,
            'stop_loss': f'Exit if NIFTY falls below {atm - 250}',
            'rationale': f'BANKNIFTY {bn_chg:+.2f}% shows banking strength. Support expected near {atm - 200}.',
        })

    if nifty_chg < -0.5:
        strategies.append({
            'name': 'Bear Call Spread',
            'bias': 'BEARISH',
            'confidence': 'MEDIUM',
            'legs': [
                {'action': 'SELL', 'strike': atm + 100, 'type': 'CE', 'lot': 25},
                {'action': 'BUY', 'strike': atm + 300, 'type': 'CE', 'lot': 25},
            ],
            'max_profit': 'Premium received × 25',
            'max_loss': f'₹{(200 * 25):,}/lot minus premium',
            'stop_loss': f'Exit if NIFTY breaks above {atm + 250}',
            'rationale': f'NIFTY down {nifty_chg:.2f}% — bearish momentum, resistance at {atm + 200}.',
        })

    strategies.append({
        'name': 'Long Straddle (Event Only)',
        'bias': 'VOLATILITY PLAY',
        'confidence': 'LOW (use only around events)',
        'legs': [
            {'action': 'BUY', 'strike': atm, 'type': 'CE', 'lot': 25},
            {'action': 'BUY', 'strike': atm, 'type': 'PE', 'lot': 25},
        ],
        'max_profit': 'Unlimited',
        'max_loss': 'Total premium paid',
        'rationale': f'Only if VIX spikes above 15 or major event (RBI policy, US Fed, earnings). Current VIX {vix:.1f}.',
    })

    ce_greeks = calculate_option_greeks(spot, atm, 3, 0.12, 'CE')
    pe_greeks = calculate_option_greeks(spot, atm, 3, 0.12, 'PE')

    return {
        'market_bias': bias,
        'nifty_spot': spot,
        'atm_strike': atm,
        'vix': vix,
        'vix_signal': (
            'LOW — Favor selling strategies' if vix < 14
            else 'MODERATE' if vix < 18
            else 'HIGH — Favor buying strategies / hedging'
        ),
        'strategies': strategies,
        'atm_greeks': {
            'ce': ce_greeks,
            'pe': pe_greeks,
            'strike': atm,
            'dte': 3,
        },
        'risk_warning': 'F&O trading involves substantial risk. These are analytical recommendations only. Always use stop-losses. Max 2-3% capital per trade.',
    }


# ── Lambda handler ───────────────────────────────────────────────────

def lambda_handler(event, context):
    logger.info(f'Market data request: {json.dumps(event.get("body", ""))[:200]}')

    if event.get('httpMethod') == 'OPTIONS':
        return _respond(200, '')

    try:
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body') or {}

        action = body.get('action', 'full_dashboard')
        symbol = body.get('symbol', 'NIFTY')

        handlers = {
            'indices': action_indices,
            'option_chain': lambda: action_option_chain(symbol),
            'holdings': action_holdings,
            'fund_limits': action_fund_limits,
            'funds': action_fund_limits,
            'news': action_news,
            'positions': action_positions,
            'full_dashboard': action_full_dashboard,
            'greeks': lambda: calculate_option_greeks(
                float(body.get('spot', 0)),
                float(body.get('strike', 0)),
                int(body.get('expiry_days', 1)),
                float(body.get('iv', 0.12)),
                body.get('option_type', 'CE'),
            ),
        }

        handler = handlers.get(action)
        if not handler:
            return _respond(400, {'error': f'Unknown action: {action}', 'valid_actions': list(handlers.keys())})

        result = handler()
        return _respond(200, result)

    except Exception as e:
        logger.error(f'Error in market-data lambda: {e}')
        import traceback
        traceback.print_exc()
        return _respond(500, {'error': str(e)})
