import { cn } from '../lib/utils';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';

const TICKERS = [
  { key: 'NIFTY 50', label: 'NIFTY 50', alt: 'Nifty 50' },
  { key: 'NIFTY BANK', label: 'BANKNIFTY', alt: 'Nifty Bank' },
  { key: 'INDIA VIX', label: 'INDIA VIX', isVix: true },
  { key: 'NIFTY IT', label: 'NIFTY IT' },
  { key: 'NIFTY PHARMA', label: 'PHARMA' },
  { key: 'NIFTY METAL', label: 'METAL' },
  { key: 'NIFTY FMCG', label: 'FMCG' },
  { key: 'NIFTY AUTO', label: 'AUTO' },
  { key: 'NIFTY FIN SERVICE', label: 'FIN SVC' },
  { key: 'NIFTY ENERGY', label: 'ENERGY' },
];

export default function TickerStrip({ indices = {}, marketOpen }) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-card border-b border-border overflow-x-auto">
      {TICKERS.map(t => {
        const idx = indices[t.key] || indices[t.alt] || {};
        const val = parseFloat(idx.last || 0);
        const chg = parseFloat(idx.change || 0);
        if (!val) return null;
        const up = chg >= 0;

        return (
          <div key={t.key} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-bg-dark border border-border hover:border-gold transition-colors min-w-fit">
            <span className="text-[0.6rem] text-text-muted font-semibold tracking-wider uppercase">{t.label}</span>
            <span className="text-sm font-bold font-mono">{val.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
            <span className={cn(
              'text-xs font-semibold font-mono px-1.5 py-0.5 rounded',
              up ? 'text-green bg-green-dim' : 'text-red bg-red-dim'
            )}>
              {up ? '+' : ''}{chg.toFixed(2)}%
            </span>
          </div>
        );
      })}

      <div className={cn(
        'ml-auto px-3 py-1 rounded-md text-[0.65rem] font-bold tracking-wider whitespace-nowrap border',
        marketOpen
          ? 'bg-green-dim text-green border-green/30'
          : 'bg-red-dim text-red border-red/30'
      )}>
        <Activity className="inline w-3 h-3 mr-1" />
        {marketOpen ? 'LIVE' : 'CLOSED'}
      </div>
    </div>
  );
}
