import { marked } from './vendor/marked.esm.js';
import { refUrl, uploadAttachment } from './attachments.js';

// breaks: true 是必须的——Markdown 规范里单个换行不产生换行，
// 不开启的话第一版留下的纯文本记录渲染后会连成一段
marked.use({ breaks: true, gfm: true });

export function renderMarkdown(text) {
  const box = document.createElement('div');
  box.className = 'markdown';
  box.innerHTML = marked.parse(text || '');
  return box;
}

let pasteSeq = 0;

function insertAtCursor(ta, text) {
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
  ta.selectionStart = ta.selectionEnd = start + text.length;
}

/**
 * 带「编辑 | 预览」切换的 Markdown 输入框。
 * entityType/entityId 用于粘贴图片时决定附件挂到哪个实体；
 * onError 用于把上传失败冒泡给调用方（通常是 ctx.showToast）。
 */
export function markdownField(label, value, entityType, entityId, onError) {
  const wrap = document.createElement('div');
  wrap.className = 'field md-field';

  const head = document.createElement('div');
  head.className = 'md-head';
  const title = document.createElement('span');
  title.textContent = label;
  const tabs = document.createElement('span');
  tabs.className = 'md-tabs';
  const editTab = document.createElement('button');
  editTab.type = 'button';
  editTab.textContent = '编辑';
  const prevTab = document.createElement('button');
  prevTab.type = 'button';
  prevTab.textContent = '预览';
  tabs.append(editTab, prevTab);
  head.append(title, tabs);

  const ta = document.createElement('textarea');
  ta.className = 'md-input';
  ta.value = value ?? '';
  const preview = document.createElement('div');
  preview.className = 'md-preview hidden';

  function show(mode) {
    const previewing = mode === 'preview';
    if (previewing) {
      preview.innerHTML = '';
      preview.appendChild(renderMarkdown(ta.value));
    }
    ta.classList.toggle('hidden', previewing);
    preview.classList.toggle('hidden', !previewing);
    editTab.classList.toggle('active', !previewing);
    prevTab.classList.toggle('active', previewing);
  }
  editTab.onclick = () => show('edit');
  prevTab.onclick = () => show('preview');
  show('edit');

  ta.addEventListener('paste', async (e) => {
    const item = [...(e.clipboardData?.items || [])]
      .find((it) => it.type.startsWith('image/'));
    if (!item) return;              // 普通文本粘贴走浏览器默认行为
    const file = item.getAsFile();
    if (!file) return;
    e.preventDefault();
    // 用带序号的占位符，避免并发粘贴时替换错位置
    const token = `上传中#${++pasteSeq}`;
    insertAtCursor(ta, `![${token}]()`);
    try {
      const saved = await uploadAttachment(entityType, entityId, file);
      ta.value = ta.value.replace(`![${token}]()`,
        `![${saved.filename}](${refUrl(saved.id)})`);
    } catch (err) {
      ta.value = ta.value.replace(`![${token}]()`, '');
      onError(err.message);
    }
  });

  wrap.append(head, ta, preview);
  return { el: wrap, get: () => ta.value };
}
