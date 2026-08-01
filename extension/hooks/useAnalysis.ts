/**
 * useAnalysis Hook
 * =================
 * React hook for triggering and managing email analysis state.
 */

import { useState, useCallback } from 'react';
import type { AnalyzeResponse } from '../services/api';

interface AnalysisState {
  result: AnalyzeResponse | null;
  isLoading: boolean;
  error: string | null;
}

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({
    result: null,
    isLoading: false,
    error: null,
  });

  const analyze = useCallback(async (emailPayload: unknown) => {
    setState({ result: null, isLoading: true, error: null });
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'ANALYZE_EMAIL',
        payload: emailPayload,
      });
      if (response.success) {
        setState({ result: response.data as AnalyzeResponse, isLoading: false, error: null });
      } else {
        setState({ result: null, isLoading: false, error: response.error ?? 'Unknown error' });
      }
    } catch (err) {
      setState({ result: null, isLoading: false, error: String(err) });
    }
  }, []);

  return { ...state, analyze };
}
