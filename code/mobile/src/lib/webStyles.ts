// Web only: loads the Inter typeface and makes it the default for all text, plus a few global niceties
// (focus ring, scrollbars, text rendering). Elements that set their own fontFamily (for example monospace) keep it.
import { Platform } from 'react-native';

let done = false;

export function installWebStyles(): void {
  if (done || Platform.OS !== 'web' || typeof document === 'undefined') return;
  done = true;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap';
  document.head.appendChild(link);

  const style = document.createElement('style');
  style.setAttribute('data-scopeiq', 'global');
  style.textContent = `
    html, body { background: #EFF4FA; }
    body { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; text-rendering: optimizeLegibility; }
    [class^="css-text-"]:not([class*="r-fontFamily-"]),
    [class*=" css-text-"]:not([class*="r-fontFamily-"]),
    [class^="css-textinput-"]:not([class*="r-fontFamily-"]),
    [class*=" css-textinput-"]:not([class*="r-fontFamily-"]) {
      font-family: Inter, "Segoe UI", system-ui, -apple-system, sans-serif;
      font-feature-settings: "cv11", "ss01";
    }
    input:focus, textarea:focus { outline: none; }
    [role="button"]:focus-visible, [role="tab"]:focus-visible, a:focus-visible { outline: 2px solid #2563EB; outline-offset: 2px; border-radius: 6px; }
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 8px; border: 2px solid transparent; background-clip: content-box; }
    ::-webkit-scrollbar-thumb:hover { background: #94A3B8; border: 2px solid transparent; background-clip: content-box; }
    ::-webkit-scrollbar-track { background: transparent; }
    @keyframes siq-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
    .siq-skeleton { animation: siq-pulse 1.4s ease-in-out infinite; }
  `;
  document.head.appendChild(style);
}
