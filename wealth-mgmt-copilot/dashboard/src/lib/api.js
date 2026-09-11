const API_URL = import.meta.env.VITE_API_URL || 'https://av9tutyi9h.execute-api.us-west-2.amazonaws.com/prod';

export async function apiPost(endpoint, body) {
  const resp = await fetch(API_URL + endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API ${resp.status}`);
  return resp.json();
}

export function fetchDashboard(symbol = 'NIFTY') {
  return apiPost('/market-data', { action: 'full_dashboard', symbol });
}

export function fetchIndices() {
  return apiPost('/market-data', { action: 'indices' });
}

export function fetchOptionChain(symbol, expiry) {
  return apiPost('/market-data', { action: 'option_chain', symbol, expiry: expiry || undefined });
}

export function fetchHoldings() {
  return apiPost('/market-data', { action: 'holdings' });
}

export function fetchFunds() {
  return apiPost('/market-data', { action: 'fund_limits' });
}

export function fetchNews() {
  return apiPost('/market-data', { action: 'news' });
}

export function fetchAgentAnalysis(message) {
  return apiPost('/agent', { message });
}
