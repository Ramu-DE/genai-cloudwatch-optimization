import { useState, useCallback } from 'react';
import { fetchAgentAnalysis } from '../lib/api';

export function useAgent() {
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const analyze = useCallback(async (prompt) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAgentAnalysis(prompt);
      setResponse(result);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { response, loading, error, analyze };
}
