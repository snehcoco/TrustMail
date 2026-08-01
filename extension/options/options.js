'use strict';

const DEFAULTS = {
  backendUrl: 'http://127.0.0.1:8000',
  includeExplanations: true,
  autoScan: true,
  notifyOnPhishing: true,
  maxHistoryItems: 100,
  theme: 'dark',
};

function loadSettings() {
  chrome.storage.local.get(['trustmail_settings'], (result) => {
    const s = Object.assign({}, DEFAULTS, result.trustmail_settings || {});
    document.getElementById('backendUrl').value = s.backendUrl;
    document.getElementById('autoScan').checked = s.autoScan;
    document.getElementById('includeExplanations').checked = s.includeExplanations;
    document.getElementById('notifyOnPhishing').checked = s.notifyOnPhishing;
    document.getElementById('maxHistoryItems').value = s.maxHistoryItems;
    testConnection();
  });
}

function saveSettings() {
  const s = {
    backendUrl: document.getElementById('backendUrl').value.trim().replace(/\/$/, ''),
    autoScan: document.getElementById('autoScan').checked,
    includeExplanations: document.getElementById('includeExplanations').checked,
    notifyOnPhishing: document.getElementById('notifyOnPhishing').checked,
    maxHistoryItems: parseInt(document.getElementById('maxHistoryItems').value, 10) || 100,
    theme: 'dark',
  };
  chrome.storage.local.set({ trustmail_settings: s }, () => {
    showToast('✓ Settings saved');
  });
}

function testConnection() {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  const ver = document.getElementById('status-version');
  const url = (document.getElementById('backendUrl').value.trim() || DEFAULTS.backendUrl);

  dot.className = 'status-dot checking';
  txt.textContent = 'Checking...';
  txt.style.color = 'var(--muted)';
  ver.textContent = '';

  fetch(url + '/health', { signal: AbortSignal.timeout(5000) })
    .then(r => r.json())
    .then(data => {
      dot.className = 'status-dot online';
      txt.textContent = 'Connected — ' + (data.status || 'ok');
      txt.style.color = 'var(--safe)';
      ver.textContent = 'v' + (data.version || '?') + ' · ' + (data.models_loaded ? 'Models ✓' : 'Models not loaded');
    })
    .catch(() => {
      dot.className = 'status-dot offline';
      txt.textContent = 'Cannot reach backend';
      txt.style.color = 'var(--danger)';
      ver.textContent = 'Start: cd backend && python app.py';
    });
}

function clearHistory() {
  if (!confirm('Clear all scan history?')) return;
  chrome.storage.local.remove(['trustmail_history'], () => showToast('✓ History cleared'));
}

function resetSettings() {
  if (!confirm('Reset all settings to defaults?')) return;
  chrome.storage.local.set({ trustmail_settings: DEFAULTS }, () => {
    loadSettings();
    showToast('✓ Reset to defaults');
  });
}

function exportSettings() {
  chrome.storage.local.get(['trustmail_settings'], (r) => {
    const blob = new Blob([JSON.stringify(r.trustmail_settings || DEFAULTS, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'trustmail-settings.json';
    a.click();
    URL.revokeObjectURL(url);
  });
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

document.addEventListener('DOMContentLoaded', () => {
  loadSettings();

  document.getElementById('btn-save').addEventListener('click', saveSettings);
  document.getElementById('btn-test').addEventListener('click', testConnection);
  document.getElementById('btn-clear-history').addEventListener('click', clearHistory);
  document.getElementById('btn-reset').addEventListener('click', resetSettings);
  document.getElementById('btn-reset-footer').addEventListener('click', resetSettings);
  document.getElementById('btn-export').addEventListener('click', exportSettings);
});
