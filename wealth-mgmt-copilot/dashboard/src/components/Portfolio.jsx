import { RefreshCw } from 'lucide-react';
import { cn, fmtCurrency } from '../lib/utils';

export default function Portfolio({ holdings = null, funds = null, onRefresh }) {
  const list = Array.isArray(holdings) ? holdings : (holdings?.holdings || []);
  const margin = parseFloat(funds?.available_balance || funds?.total_margin || 0);
  const collateral = parseFloat(funds?.collateral || 0);

  return (
    <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-sm font-bold">💰 Portfolio & Margin</span>
        {onRefresh && (
          <button onClick={onRefresh} className="text-text-muted hover:text-gold transition">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <div className="p-3">
        {/* Margin cards */}
        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="bg-bg-dark p-2 rounded-lg border border-border">
            <div className="text-[0.6rem] text-text-muted uppercase font-bold">Available Margin</div>
            <div className="text-sm font-mono font-bold mt-0.5">{fmtCurrency(margin)}</div>
          </div>
          <div className="bg-bg-dark p-2 rounded-lg border border-border">
            <div className="text-[0.6rem] text-text-muted uppercase font-bold">Collateral</div>
            <div className="text-sm font-mono font-bold mt-0.5">{fmtCurrency(collateral)}</div>
          </div>
        </div>

        {/* Holdings table */}
        <div className="text-[0.6rem] text-text-muted uppercase font-bold mb-1">Holdings ({list.length})</div>
        <div className="max-h-[140px] overflow-y-auto">
          <table className="w-full text-[0.68rem]">
            <thead>
              <tr className="text-text-muted text-[0.6rem] uppercase border-b border-border">
                <th className="text-left py-1 px-1 font-semibold">Stock</th>
                <th className="text-right py-1 px-1 font-semibold">Qty</th>
                <th className="text-right py-1 px-1 font-semibold">Avg</th>
                <th className="text-right py-1 px-1 font-semibold">LTP</th>
                <th className="text-right py-1 px-1 font-semibold">P&L</th>
              </tr>
            </thead>
            <tbody>
              {list.length === 0 && (
                <tr><td colSpan={5} className="text-center py-4 text-text-muted">No holdings</td></tr>
              )}
              {list.map((h, i) => {
                const pnl = parseFloat(h.pnl || 0);
                return (
                  <tr key={i} className="border-b border-border/20 hover:bg-bg-card-hover transition-colors">
                    <td className="py-0.5 px-1 font-semibold font-mono">{h.ticker || h.tradingSymbol || '--'}</td>
                    <td className="text-right py-0.5 px-1 font-mono">{h.quantity || 0}</td>
                    <td className="text-right py-0.5 px-1 font-mono text-text-muted">{parseFloat(h.avg_price || h.avgCostPrice || 0).toFixed(1)}</td>
                    <td className="text-right py-0.5 px-1 font-mono">{parseFloat(h.current_price || h.lastTradedPrice || 0).toFixed(1)}</td>
                    <td className={cn('text-right py-0.5 px-1 font-mono font-semibold', pnl >= 0 ? 'text-green' : 'text-red')}>
                      {pnl >= 0 ? '+' : ''}{pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
