import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchDashboard, fetchOptionChain } from '../lib/api';
import { isMarketOpen } from '../lib/utils';

export function useMarketData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef(null);
  const cdRef = useRef(null);

  const refresh = useCallback(async (symbol = 'NIFTY') => {
    try {
      const result = await fetchDashboard(symbol);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = isMarketOpen() ? 30000 : 300000;
    setCountdown(Math.floor(interval / 1000));

    timerRef.current = setInterval(() => {
      refresh();
      setCountdown(Math.floor(interval / 1000));
    }, interval);

    cdRef.current = setInterval(() => {
      setCountdown(c => Math.max(0, c - 1));
    }, 1000);

    return () => {
      clearInterval(timerRef.current);
      clearInterval(cdRef.current);
    };
  }, [refresh]);

  return { data, loading, error, countdown, refresh };
}

export function useOptionChain(symbol, expiry) {
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchOptionChain(symbol, expiry);
      setChain(result);
    } catch (e) {
      console.error('Option chain fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, [symbol, expiry]);

  useEffect(() => { refresh(); }, [refresh]);

  return { chain, loading, refresh };
}
