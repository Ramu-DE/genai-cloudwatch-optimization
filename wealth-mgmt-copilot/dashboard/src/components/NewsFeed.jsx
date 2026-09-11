import { useState } from 'react';
import { ExternalLink, Newspaper } from 'lucide-react';
import { cn } from '../lib/utils';

const FILTERS = ['All', 'Market', 'Economy', 'Stocks', 'FII'];

export default function NewsFeed({ news = null }) {
  const [filter, setFilter] = useState('All');
  const articles = Array.isArray(news) ? news : (news?.articles || []);

  const filtered = filter === 'All'
    ? articles
    : articles.filter(a => {
        const text = (a.title + ' ' + (a.summary || '')).toLowerCase();
        return text.includes(filter.toLowerCase());
      });

  return (
    <div className="px-4 pb-4">
      <div className="flex items-center gap-3 mb-2">
        <span className="font-bold text-sm flex items-center gap-1.5">
          <Newspaper className="w-4 h-4 text-blue" /> Market News
        </span>
        <div className="flex gap-1 ml-3">
          {FILTERS.map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={cn(
                'px-2.5 py-0.5 rounded-full text-[0.65rem] font-medium border transition',
                f === filter
                  ? 'bg-gold text-bg-dark border-gold'
                  : 'bg-bg-card text-text-muted border-border hover:text-text-primary'
              )}>{f}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
        {filtered.length === 0 && (
          <div className="text-text-muted text-xs py-4">No news available</div>
        )}
        {filtered.slice(0, 12).map((item, i) => (
          <a key={i} href={item.link} target="_blank" rel="noopener noreferrer"
            className="bg-bg-card border border-border rounded-lg p-2.5 hover:border-blue transition-colors group block">
            <div className="text-xs font-semibold leading-snug mb-1 group-hover:text-blue transition-colors line-clamp-2">
              {item.title}
            </div>
            <div className="flex items-center gap-1 text-[0.6rem] text-text-muted">
              <span>{item.source}</span>
              <span>·</span>
              <span>{item.published || item.time_ago || ''}</span>
              <ExternalLink className="w-2.5 h-2.5 ml-auto opacity-0 group-hover:opacity-100 transition" />
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
