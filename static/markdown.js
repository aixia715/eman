import { marked } from './vendor/marked.esm.js';

// breaks: true 是必须的——Markdown 规范里单个换行不产生换行，
// 不开启的话第一版留下的纯文本记录渲染后会连成一段
marked.use({ breaks: true, gfm: true });

export function renderMarkdown(text) {
  const box = document.createElement('div');
  box.className = 'markdown';
  box.innerHTML = marked.parse(text || '');
  return box;
}
