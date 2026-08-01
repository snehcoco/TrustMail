/**
 * useTheme Hook
 * ==============
 * Dark/light theme with persistence via chrome.storage.
 */

import { useState, useEffect } from 'react';
import { StorageService } from '../services/storage';

type Theme = 'dark' | 'light';

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('dark');

  useEffect(() => {
    StorageService.getSettings().then((s) => setTheme(s.theme));
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    StorageService.saveSettings({ theme: next });
  };

  return { theme, toggle };
}
