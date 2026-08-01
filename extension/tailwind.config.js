/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './popup/**/*.{ts,tsx,html}',
    './options/**/*.{ts,tsx,html}',
    './components/**/*.{ts,tsx}',
    './pages/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
    './services/**/*.{ts,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        brand: {
          cyan: '#06b6d4',
          blue: '#3b82f6',
          purple: '#8b5cf6',
        },
        risk: {
          safe: '#22c55e',
          low: '#84cc16',
          suspicious: '#f59e0b',
          phishing: '#ef4444',
          dangerous: '#dc2626',
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        scan: 'pulse-scan 1.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
