import { cn, bsGreeks } from '../lib/utils';

export default function MarketSummary({ indices = {}, chain = null }) {
  const nifty = indices['NIFTY 50'] || {};
  const vix = indices['INDIA VIX'] || {};
  const vixVal = parseFloat(vix.last || 0);

  let vixSignal = 'LOW — Sell strategies favorable';
  let vixColor = 'text-green';
  if (vixVal >= 18) { vixSignal = 'HIGH — Buy strategies / hedging'; vixColor = 'text-red'; }
  else if (vixVal >= 14) { vixSignal = 'MODERATE — Cautious positioning'; vixColor = 'text-gold'; }

  const pcr = chain?.pcr || 0;
  const pcrLabel = pcr > 1.2 ? 'Bullish' : pcr < 0.8 ? 'Bearish' : 'Neutral';

  const spot = chain?.underlying_price || parseFloat(nifty.last || 0);
  const step = 50;
  const atm = Math.round(spot / step) * step;
  const strikes = chain?.strikes || [];
  const atmData = strikes.find(s => (s.strike_price || s.strike) === atm);
  let iv = 0.12;
  if (atmData?.ce_iv > 0) iv = atmData.ce_iv / 100;
  let dte = 3;
  if (chain?.expiry) {
    try {
      const months = { Jan:0, Feb:1, Mar:2, Apr:3, May:4, Jun:5, Jul:6, Aug:7, Sep:8, Oct:9, Nov:10, Dec:11 };
      const parts = chain.expiry.split('-');
      const expDate = new Date(parseInt(parts[2]), months[parts[1]], parseInt(parts[0]));
      dte = Math.max(1, Math.ceil((expDate - new Date()) / 86400000));
    } catch (e) {}
  }
  const greeks = spot > 0 ? bsGreeks(spot, atm, dte, iv, 'CE') : null;

  return (
    <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b border-border">
        <span className="text-sm font-bold">📊 Market Summary & Greeks</span>
      </div>
      <div className="p-3 space-y-1">
        <Row label="Day Range" value={nifty.high && nifty.low
          ? `${parseFloat(nifty.low).toLocaleString('en-IN')} — ${parseFloat(nifty.high).toLocaleString('en-IN')} (${(parseFloat(nifty.high) - parseFloat(nifty.low)).toFixed(0)} pts)`
          : '--'
        } />
        <Row label="VIX Signal" value={vixSignal} className={vixColor} />
        <Row label="PCR Trend" value={`${pcr.toFixed(2)} (${pcrLabel})`} />
        <Row label="Support" value={chain?.support || '--'} className="text-green" />
        <Row label="Resistance" value={chain?.resistance || '--'} className="text-red" />

        {greeks && (
          <>
            <div className="text-[0.65rem] text-text-muted font-bold uppercase mt-3 mb-1">ATM Greeks ({atm}) · {dte}d to expiry</div>
            <div className="grid grid-cols-2 gap-1.5">
              <Greek name="Delta" value={greeks.delta.toFixed(4)} desc={`₹${Math.abs(greeks.delta).toFixed(2)}/₹1 move`} />
              <Greek name="Gamma" value={greeks.gamma.toFixed(6)} desc={`Δ chg ${greeks.gamma.toFixed(4)}/₹1`} />
              <Greek name="Theta" value={greeks.theta.toFixed(2)} desc={`Loses ₹${Math.abs(greeks.theta).toFixed(1)}/day`} />
              <Greek name="Vega" value={greeks.vega.toFixed(2)} desc={`₹${greeks.vega.toFixed(1)}/1% IV chg`} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, className }) {
  return (
    <div className="flex justify-between py-0.5 text-xs border-b border-border/20">
      <span className="text-text-secondary">{label}</span>
      <span className={cn('font-mono font-semibold', className)}>{value}</span>
    </div>
  );
}

function Greek({ name, value, desc }) {
  return (
    <div className="bg-bg-dark p-2 rounded-lg border border-border">
      <div className="text-[0.6rem] text-text-muted uppercase font-bold">{name}</div>
      <div className="text-base font-mono font-bold mt-0.5">{value}</div>
      <div className="text-[0.6rem] text-text-secondary">{desc}</div>
    </div>
  );
}
