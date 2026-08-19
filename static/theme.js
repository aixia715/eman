const STORAGE_KEY = 'eman-theme';
const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
const toggle = document.getElementById('theme-toggle');

function savedTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

function currentTheme() {
  return document.documentElement.dataset.theme ||
    (systemTheme.matches ? 'dark' : 'light');
}

function updateToggle() {
  const isDark = currentTheme() === 'dark';
  const label = isDark ? '切换为日间模式' : '切换为夜间模式';
  toggle.textContent = isDark ? '☀' : '☾';
  toggle.setAttribute('aria-label', label);
  toggle.setAttribute('aria-pressed', String(isDark));
  toggle.title = label;
}

const initialTheme = savedTheme();
if (initialTheme) document.documentElement.dataset.theme = initialTheme;
updateToggle();

toggle.addEventListener('click', () => {
  const nextTheme = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = nextTheme;
  try {
    localStorage.setItem(STORAGE_KEY, nextTheme);
  } catch {
    // 浏览器禁止本地存储时，本次切换仍然有效。
  }
  updateToggle();
});

systemTheme.addEventListener('change', () => {
  if (!savedTheme()) updateToggle();
});
