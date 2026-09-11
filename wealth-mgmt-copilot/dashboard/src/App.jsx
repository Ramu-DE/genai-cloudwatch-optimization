import { Shield, Clock, RefreshCw } from 'lucide-react';
import { useMarketData } from './hooks/useMarketData';
import { isMarketOpen, getISTString } from './lib/utils';
import TickerStrip from './components/TickerStrip';
import OptionChain from './components/OptionChain';
import AgentPanel from './components/AgentPanel';
import MarketSummary from './components/MarketSummary';
import Portfolio from './components/Portfolio';
import NewsFeed from './components/NewsFeed';

export default function App() {
  const { data, loading, countdown, refresh } = useMarketData();
  const marketOpen = data?.market_status?.market_open ?? isMarketOpen();
  const indices = data?.indices || {};

  return (
    <div className="min-h-screen flex flex-col">
      {/* Navbar */}
      <header className="bg-gradient-to-r from-[#080c12] to-[#0f1520] px-4 py-2 flex items-center justify-between border-b border-border sticky top-0 z-50">
        <div className="flex items-center gap-2.5">
          <span className="text-xl">📈</span>
          <span className="text-base font-bold tracking-tight">
            F&O <span className="text-gold">Trading</span> Dashboard
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="text-text-muted font-mono">{getISTString()}</span>
          <div className="flex items-center gap-1.5 text-gold font-mono font-semibold">
            <Clock className="w-3 h-3" />
            {countdown > 0 ? `${countdown}s` : '...'}
          </div>
          <button onClick={() => refresh()} className="text-text-muted hover:text-gold transition cursor-pointer">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Disclaimer */}
      <div className="bg-gold/5 border-b border-gold/20 px-4 py-1 text-center">
        <span className="text-[0.65rem] text-gold font-medium tracking-wide flex items-center justify-center gap-1.5">
          <Shield className="w-3 h-3" />
          READ-ONLY ANALYSIS — Analyzes and recommends but NEVER places orders. Execute trades on your Dhan platform.
        </span>
      </div>

      {/* Ticker Strip */}
      <TickerStrip indices={indices} marketOpen={marketOpen} />

      {/* Main Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-3 p-3 flex-1">
        {/* Left: Option Chain */}
        <OptionChain spot={data?.nifty_spot || 0} />

        {/* Right: Stacked panels */}
        <div className="flex flex-col gap-3">
          <AgentPanel
            indices={indices}
            precomputed={data?.agent_analysis}
          />
          <MarketSummary indices={indices} />
          <Portfolio
            holdings={data?.holdings}
            funds={data?.fund_limits}
            onRefresh={refresh}
          />
        </div>
      </div>

      {/* News */}
      <NewsFeed news={data?.news} />
    </div>
  );
}
