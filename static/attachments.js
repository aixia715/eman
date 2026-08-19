import API from './api.js';

const UPLOAD_PATH = { experiment: '/experiments/', run: '/runs/',
                      group: '/groups/', attempt: '/attempts/' };

export function uploadAttachment(entityType, entityId, file) {
  return API.upload(`${UPLOAD_PATH[entityType]}${entityId}/attachments`, file);
}

export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function refUrl(id) { return `/api/attachments/${id}`; }

/**
 * 四级通用的附件区。onChange 由调用方提供，用于在增删后刷新详情数据。
 */
export function attachmentSection(ctx, entityType, obj, onChange) {
  const box = document.createElement('section');
  box.className = 'attachments';
  const h = document.createElement('h3');
  h.textContent = '附件';
  box.appendChild(h);

  const hint = document.createElement('p');
  hint.className = 'placeholder';
  hint.textContent = '小文件（截图、配置、导出的小 csv）放这里，单个上限 50 MB；'
    + '大体积原始数据请填写数据目录。';
  box.appendChild(hint);

  const list = document.createElement('ul');
  list.className = 'attachment-list';
  const items = obj.attachments || [];
  if (items.length === 0) {
    const empty = document.createElement('li');
    empty.className = 'placeholder';
    empty.textContent = '（无）';
    list.appendChild(empty);
  }
  for (const att of items) {
    const li = document.createElement('li');
    const link = document.createElement('a');
    link.href = refUrl(att.id);
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = att.filename;
    const size = document.createElement('span');
    size.className = 'attachment-size';
    size.textContent = formatSize(att.size);

    const copy = document.createElement('button');
    copy.type = 'button';
    copy.textContent = '复制引用';
    copy.onclick = async () => {
      const text = `![${att.filename}](${refUrl(att.id)})`;
      try {
        await navigator.clipboard.writeText(text);
        ctx.showToast('已复制引用，粘贴到正文即可显示');
      } catch {
        ctx.showToast('复制失败，请手工输入：' + text);
      }
    };

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'danger';
    del.textContent = '删除';
    del.onclick = () => removeAttachment(ctx, att, onChange);

    li.append(link, size, copy, del);
    list.appendChild(li);
  }
  box.appendChild(list);

  const picker = document.createElement('input');
  picker.type = 'file';
  picker.onchange = async () => {
    const file = picker.files && picker.files[0];
    if (!file) return;
    try {
      await uploadAttachment(entityType, obj.id, file);
      await onChange();
    } catch (err) {
      ctx.showToast(err.message);
    } finally {
      // 失败路径下 picker 不会被 onChange() 的重建换掉，必须手动清空 value，
      // 否则用户排障后再选同一个文件浏览器不会触发 change 事件，表现为静默无响应
      picker.value = '';
    }
  };
  box.appendChild(picker);
  return box;
}

async function removeAttachment(ctx, att, onChange) {
  try {
    // 删除前先问后端：正文里还有多少处在引用它
    const { count } = await API.get(`/attachments/${att.id}/references`);
    const extra = count > 0
      ? `\n该附件被正文引用 ${count} 处，删除后这些位置将显示为裂图。` : '';
    if (!window.confirm(
      `确定删除附件「${att.filename}」吗？${extra}\n此操作不可恢复。`)) return;
    await API.del(`/attachments/${att.id}`);
    await onChange();
  } catch (err) { ctx.showToast(err.message); }
}
