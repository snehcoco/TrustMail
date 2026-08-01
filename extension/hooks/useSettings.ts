/**
 * useSettings Hook
 * =================
 * Reads and writes TrustMail settings from chrome.storage.
 */

import { useState, useEffect, useCallback } from 'react';
import { StorageService, type TrustMailSettings } from '../services/storage';

export function useSettings() {
  const [settings, setSettings] = useState<TrustMailSettings | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    StorageService.getSettings().then((s) => {
      setSettings(s);
      setLoading(false);
    });
  }, []);

  const save = useCallback(async (updates: Partial<TrustMailSettings>) => {
    await StorageService.saveSettings(updates);
    const updated = await StorageService.getSettings();
    setSettings(updated);
  }, []);

  return { settings: settings ?? ({} as TrustMailSettings), loading, save };
}
