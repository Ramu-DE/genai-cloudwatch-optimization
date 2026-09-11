import { useState } from 'react';
import { Bot, Loader2, Send, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { useAgent } from '../hooks/useAgent';
import { cn } from '../lib/utils';

export default function AgentPanel({ indices = {}, precomputed = null }) {
  const { response, loading, analyze } = useAgent();
  const [mode, setMode] = useState('fno');

  const nifty = indices['NIFTY 50'] || {};
  const vix = indices['INDIA VIX'] || {};
  const bank = indices['NIFTY BANK'] || {};

  async function handleAnalyze() {
    const prompt = mode === 'fno'
      ? `Analyze NIFTY and BANKNIFTY for F&O trading right now. Current data:
- NIFTY: ${nifty.last || 'N/A'} (${nifty.change || 'N/A'}%)
- BANKNIFTY: ${bank.last || 'N/A'} (${bank.change || 'N/A'}%)
- VIX: ${vix.last || 'N/A'} (${vix.change || 'N/A'}%)
- Day Range: ${nifty.low || 'N/A'} - ${nifty.high || 'N/A'}

Give me 2-3 specific F&O strategy recommendations with exact strikes, lot sizes, max profit, max loss, breakevens, and stop-loss. Factor in VIX for strategy selection.`
      : `Analyze the Indian equity market for intraday trading opportunities right now. Current data:
- NIFTY: ${nifty.last || 'N/A'} (${nifty.change || 'N/A'}%)
- BANKNIFTY: ${bank.last || 'N/A'} (${bank.change || 'N/A'}%)
- VIX: ${vix.last || 'N/A'}
- Sector performance: IT ${indices['NIFTY IT']?.change || 'N/A'}%, Pharma ${indices['NIFTY PHARMA']?.change || 'N/A'}%, Metal ${indices['NIFTY METAL']?.change || 'N/A'}%, Auto ${indices['NIFTY AUTO']?.change || 'N/A'}%, Bank ${bank.change || 'N/A'}%, FMCG ${indices['NIFTY FMCG']?.change || 'N/A'}%

Identify 3-4 intraday equity trade ideas: which stocks to buy/sell, entry price, target, stop-loss, and reasoning based on sector momentum and index trend. Focus on NIFTY 50 stocks with high volume.`;

    await analyze(prompt);
  }

  const display = response || (precomputed ? { response: null } : null);

  return (
    <div className="bg-bg-card border border-border rounded-xl overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-sm font-bold flex items-center gap-1.5">
          <Bot className="w-4 h-4 text-gold" /> Agent Recommendations
        </span>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-1 px-3 py-1.5 border-b border-border bg-bg-dark">
        <ModeBtn active={mode === 'fno'} onClick={() => setMode('fno')} label="F&O Strategies" />
        <ModeBtn active={mode === 'intraday'} onClick={() => setMode('intraday')} label="Equity Intraday" />
      </div>

      <div className="p-3 flex-1 overflow-y-auto max-h-[400px]">
        {/* Precomputed strategies */}
        {precomputed && !response && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[0.65rem] text-text-muted uppercase font-bold">Market Bias</span>
              <span className={cn('text-sm font-bold',
                precomputed.market_bias === 'BULLISH' ? 'text-green' :
                precomputed.market_bias === 'BEARISH' ? 'text-red' : 'text-blue'
              )}>{precomputed.market_bias}</span>
              <span className="text-[0.6rem] text-text-muted ml-auto">{precomputed.vix_signal?.split('—')[0]}</span>
            </div>
            {(precomputed.strategies || []).map((s, i) => (
              <StrategyCard key={i} strategy={s} />
            ))}
          </div>
        )}

        {/* Agent response */}
        {response && (
          <div className="text-[0.78rem] leading-relaxed text-text-secondary whitespace-pre-wrap"
            dangerouslySetInnerHTML={{ __html: formatResponse(response.response || '') }}
          />
        )}

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center py-8 gap-2">
            <Loader2 className="w-6 h-6 text-gold animate-spin" />
            <span className="text-xs text-text-muted">Analyzing market conditions...</span>
          </div>
        )}

        {/* Initial state */}
        {!loading && !response && !precomputed && (
          <div className="text-center py-6 text-text-muted text-xs">
            Click Analyze for AI-powered trading recommendations
          </div>
        )}
      </div>

      <div className="px-3 py-2 border-t border-border">
        <button onClick={handleAnalyze} disabled={loading}
          className={cn(
            'w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-semibold transition',
            loading ? 'bg-gold/30 text-gold/50 cursor-wait'
              : 'bg-gold text-bg-dark hover:bg-gold/90 cursor-pointer'
          )}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {loading ? 'Analyzing...' : `Analyze ${mode === 'fno' ? 'F&O' : 'Intraday'}`}
        </button>
      </div>
    </div>
  );
}

function ModeBtn({ active, onClick, label }) {
  return (
    <button onClick={onClick} className={cn(
      'px-3 py-1 rounded-md text-xs font-semibold transition',
      active ? 'bg-gold text-bg-dark' : 'text-text-muted hover:text-text-primary'
    )}>{label}</button>
  );
}

function StrategyCard({ strategy }) {
  return (
    <div className="bg-bg-dark border border-border rounded-lg p-2.5">
      <div className="font-bold text-gold text-sm mb-1">{strategy.name}</div>
      <div className="font-mono text-[0.7rem] space-y-0.5 mb-1">
        {(strategy.legs || []).map((leg, i) => (
          <div key={i}>
            <span className={cn('font-bold', leg.action === 'BUY' ? 'text-green' : 'text-red')}>{leg.action}</span>
            {' '}{leg.strike} {leg.type} × {leg.lot}
          </div>
        ))}
      </div>
      <div className="text-[0.7rem] text-text-secondary mb-1">{strategy.rationale}</div>
      <div className="flex gap-2 flex-wrap">
        {strategy.max_profit && <Tag color="green">Profit: {strategy.max_profit}</Tag>}
        {strategy.max_loss && <Tag color="red">Loss: {strategy.max_loss}</Tag>}
        {strategy.stop_loss && <Tag color="purple">SL: {strategy.stop_loss}</Tag>}
      </div>
    </div>
  );
}

function Tag({ color, children }) {
  const colors = {
    green: 'bg-green-dim text-green',
    red: 'bg-red-dim text-red',
    blue: 'bg-blue-dim text-blue',
    purple: 'bg-purple/10 text-purple',
  };
  return <span className={cn('text-[0.6rem] font-semibold px-1.5 py-0.5 rounded', colors[color])}>{children}</span>;
}

function formatResponse(text) {
  let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary">$1</strong>');
  html = html.replace(/^#{1,3}\s+(.+)$/gm, '<div class="font-bold text-gold mt-3 mb-1">$1</div>');
  html = html.replace(/^\|(.+)\|$/gm, (m) => `<div class="font-mono text-[0.7rem]">${m}</div>`);
  html = html.replace(/^[-*]\s+(.+)$/gm, '<div class="pl-3">• $1</div>');
  return html;
}
