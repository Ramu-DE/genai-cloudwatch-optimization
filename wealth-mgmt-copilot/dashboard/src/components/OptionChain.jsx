import { useState, useEffect, useMemo, useRef } from 'react';
import { RefreshCw, ChevronDown } from 'lucide-react';
import { cn, fmt, fmtSigned } from '../lib/utils';
import { useOptionChain } from '../hooks/useMarketData';

export default function OptionChain({ spot = 0 }) {
  const [symbol, setSymbol] = useState('NIFTY');
  const [expiry, setExpiry] = useState('');
  const { chain, loading, refresh } = useOptionChain(symbol, expiry);
  const tbodyRef = useRef(null);

  const lotSizes = { NIFTY: 25, BANKNIFTY: 15, FINNIFTY: 25, MIDCPNIFTY: 50 };
  const steps = { NIFTY: 50, BANKNIFTY: 100, FINNIFTY: 50, MIDCPNIFTY: 25 };

  const underlying = chain?.underlying_price || spot || 0;
  const step = steps[symbol] || 50;
  const atm = Math.round(underlying / step) * step;
  const strikes = chain?.strikes || [];
  const range = step * 12;
  const maxOI = Math.max(1, ...strikes.map(s => Math.max(s.ce_oi || 0, s.pe_oi || 0)));

  const filtered = useMemo(() =>
    strikes.filter(s => {
      const sp = s.strike_price || s.strike || 0;
      return sp >= atm - range && sp <= atm + range;
    }),
    [strikes, atm, range]
  );

  const pcr = chain?.pcr || 0;
  const pcrLabel = pcr > 1.2 ? 'Bullish' : pcr < 0.8 ? 'Bearish' : 'Neutral';
  const pcrColor = pcr > 1.2 ? 'text-green' : pcr < 0.8 ? 'text-red' : 'text-blue';

  useEffect(() => {
    if (!tbodyRef.current) return;
    const atmRow = tbodyRef.current.querySelector('[data-atm="true"]');
    if (atmRow) atmRow.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [filtered]);

  return (
    <div className="bg-bg-card border border-border rounded-xl overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-sm font-bold flex items-center gap-1.5">⛓ Option Chain</span>
        <button onClick={refresh} className={cn('text-text-muted hover:text-gold transition', loading && 'animate-spin')}>
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 px-3 py-1.5 bg-bg-dark border-b border-border text-xs flex-wrap">
        <label className="text-text-muted font-semibold uppercase text-[0.65rem]">Underlying</label>
        <select value={symbol} onChange={e => { setSymbol(e.target.value); setExpiry(''); }}
          className="bg-bg-card text-text-primary border border-border rounded px-2 py-1 text-xs font-mono">
          {Object.keys(lotSizes).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="text-text-muted font-semibold uppercase text-[0.65rem]">Expiry</label>
        <select value={expiry} onChange={e => setExpiry(e.target.value)}
          className="bg-bg-card text-text-primary border border-border rounded px-2 py-1 text-xs font-mono">
          <option value="">Nearest</option>
          {(chain?.all_expiries || []).map(e => <option key={e} value={e}>{e}</option>)}
        </select>
        <span className="text-text-muted font-semibold uppercase text-[0.65rem] ml-2">Spot</span>
        <span className="font-mono font-bold text-gold text-sm">{underlying.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
        <span className="text-text-muted font-semibold uppercase text-[0.65rem]">Lot</span>
        <span className="font-mono font-semibold">{chain?.lot_size || lotSizes[symbol] || '--'}</span>
      </div>

      {/* OI Summary */}
      <div className="flex items-center gap-4 px-3 py-1.5 bg-black/20 border-b border-border text-xs">
        <Stat label="CE OI" value={fmt(chain?.total_ce_oi)} />
        <Stat label="PE OI" value={fmt(chain?.total_pe_oi)} />
        <Stat label="PCR" value={pcr.toFixed(2)} className={pcrColor} />
        <span className={cn('text-[0.65rem] font-bold px-2 py-0.5 rounded', pcrColor,
          pcr > 1.2 ? 'bg-green-dim' : pcr < 0.8 ? 'bg-red-dim' : 'bg-blue-dim'
        )}>{pcrLabel}</span>
        <div className="ml-auto flex gap-4">
          <Stat label="Support" value={chain?.support || '--'} className="text-green" />
          <Stat label="Resistance" value={chain?.resistance || '--'} className="text-red" />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-auto max-h-[520px] flex-1">
        <table className="w-full border-collapse text-[0.68rem] font-mono">
          <thead className="sticky top-0 z-10">
            <tr className="bg-bg-card">
              <th className="text-right px-1.5 py-1 text-red/70 font-semibold border-b-2 border-border text-[0.6rem]">OI</th>
              <th className="text-right px-1.5 py-1 text-red/70 font-semibold border-b-2 border-border text-[0.6rem]">Chg</th>
              <th className="text-right px-1.5 py-1 text-red/70 font-semibold border-b-2 border-border text-[0.6rem]">Vol</th>
              <th className="text-right px-1.5 py-1 text-red/70 font-semibold border-b-2 border-border text-[0.6rem]">IV%</th>
              <th className="text-right px-1.5 py-1 text-red/70 font-semibold border-b-2 border-border text-[0.6rem]">LTP</th>
              <th className="text-center px-2 py-1 bg-gold text-bg-dark font-extrabold border-b-2 border-gold text-[0.65rem]">STRIKE</th>
              <th className="text-right px-1.5 py-1 text-green/70 font-semibold border-b-2 border-border text-[0.6rem]">LTP</th>
              <th className="text-right px-1.5 py-1 text-green/70 font-semibold border-b-2 border-border text-[0.6rem]">IV%</th>
              <th className="text-right px-1.5 py-1 text-green/70 font-semibold border-b-2 border-border text-[0.6rem]">Vol</th>
              <th className="text-right px-1.5 py-1 text-green/70 font-semibold border-b-2 border-border text-[0.6rem]">Chg</th>
              <th className="text-right px-1.5 py-1 text-green/70 font-semibold border-b-2 border-border text-[0.6rem]">OI</th>
            </tr>
          </thead>
          <tbody ref={tbodyRef}>
            {filtered.length === 0 && (
              <tr><td colSpan={11} className="text-center py-10 text-text-muted">
                {loading ? 'Loading option chain...' : 'Option chain data unavailable'}
              </td></tr>
            )}
            {filtered.map(s => {
              const sp = s.strike_price || s.strike || 0;
              const isATM = sp === atm;
              const ceBarW = Math.round((s.ce_oi || 0) / maxOI * 50);
              const peBarW = Math.round((s.pe_oi || 0) / maxOI * 50);
              return (
                <tr key={sp} data-atm={isATM || undefined}
                  className={cn(
                    'border-b border-border/30 hover:bg-bg-card-hover transition-colors',
                    isATM && 'bg-gold/8',
                    sp < underlying && 'bg-red/3',
                    sp > underlying && 'bg-green/3',
                  )}>
                  <td className="text-right px-1.5 py-0.5">
                    <span className="inline-block h-2 rounded-sm bg-red/30 mr-1 align-middle" style={{ width: ceBarW }} />
                    {fmt(s.ce_oi)}
                  </td>
                  <OIChange val={s.ce_oi_change || s.ce_chg_oi} />
                  <td className="text-right px-1.5 py-0.5 text-text-muted">{fmt(s.ce_volume)}</td>
                  <td className="text-right px-1.5 py-0.5 text-text-muted">{(s.ce_iv || 0).toFixed(1)}</td>
                  <td className="text-right px-1.5 py-0.5 font-semibold">{(s.ce_ltp || 0).toFixed(2)}</td>
                  <td className={cn(
                    'text-center px-2 py-0.5 font-bold border-x-2 border-gold/40',
                    isATM ? 'bg-gold text-bg-dark font-extrabold text-sm' : 'text-gold'
                  )}>
                    {sp.toLocaleString('en-IN')}
                  </td>
                  <td className="text-right px-1.5 py-0.5 font-semibold">{(s.pe_ltp || 0).toFixed(2)}</td>
                  <td className="text-right px-1.5 py-0.5 text-text-muted">{(s.pe_iv || 0).toFixed(1)}</td>
                  <td className="text-right px-1.5 py-0.5 text-text-muted">{fmt(s.pe_volume)}</td>
                  <OIChange val={s.pe_oi_change || s.pe_chg_oi} />
                  <td className="text-right px-1.5 py-0.5">
                    {fmt(s.pe_oi)}
                    <span className="inline-block h-2 rounded-sm bg-green/30 ml-1 align-middle" style={{ width: peBarW }} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value, className }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-text-muted font-medium">{label}:</span>
      <span className={cn('font-mono font-semibold', className)}>{value}</span>
    </div>
  );
}

function OIChange({ val }) {
  val = val || 0;
  return (
    <td className={cn('text-right px-1.5 py-0.5', val > 0 ? 'text-green' : val < 0 ? 'text-red' : 'text-text-muted')}>
      {fmtSigned(val)}
    </td>
  );
}
