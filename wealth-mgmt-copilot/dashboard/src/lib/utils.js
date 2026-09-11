export function getISTNow() {
  const now = new Date();
  return new Date(now.getTime() + (330 - now.getTimezoneOffset()) * 60000);
}

export function isMarketOpen() {
  const ist = getISTNow();
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;
  const mins = ist.getHours() * 60 + ist.getMinutes();
  return mins >= 555 && mins <= 930;
}

export function getISTString() {
  const ist = getISTNow();
  return ist.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' IST';
}

export function fmt(n) {
  return (n || 0).toLocaleString('en-IN');
}

export function fmtCurrency(n) {
  const abs = Math.abs(n || 0);
  if (abs >= 10000000) return '₹' + (n / 10000000).toFixed(2) + 'Cr';
  if (abs >= 100000) return '₹' + (n / 100000).toFixed(2) + 'L';
  return '₹' + fmt(Math.round(n));
}

export function fmtSigned(n) {
  n = n || 0;
  return (n > 0 ? '+' : '') + n.toLocaleString('en-IN');
}

export function cn(...classes) {
  return classes.filter(Boolean).join(' ');
}

export function bsGreeks(spot, strike, dte, iv, type = 'CE') {
  const T = dte / 365;
  const r = 0.065;
  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(spot / strike) + (r + 0.5 * iv * iv) * T) / (iv * sqrtT);
  const d2 = d1 - iv * sqrtT;
  const nd1 = normCDF(d1);
  const npd1 = normPDF(d1);

  let delta, theta;
  if (type === 'CE') {
    delta = nd1;
    theta = (-spot * npd1 * iv / (2 * sqrtT) - r * strike * Math.exp(-r * T) * normCDF(d2)) / 365;
  } else {
    delta = nd1 - 1;
    theta = (-spot * npd1 * iv / (2 * sqrtT) + r * strike * Math.exp(-r * T) * normCDF(-d2)) / 365;
  }
  return { delta, gamma: npd1 / (spot * iv * sqrtT), theta, vega: spot * npd1 * sqrtT / 100 };
}

function normCDF(x) { return 0.5 * (1 + erf(x / Math.SQRT2)); }
function normPDF(x) { return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI); }
function erf(x) {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  x = Math.abs(x);
  const t = 1 / (1 + p * x);
  return sign * (1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x));
}
