import API from './api.js';
import { markdownField, renderMarkdown } from './markdown.js';
import { attachmentSection } from './attachments.js';

const DEL_PATH = { experiment: '/experiments/', run: '/runs/',
                   group: '/groups/', attempt: '/attempts/' };

export function renderDetail(ctx) {
  const root = document.getElementById('detail');
  const { state } = ctx;
  root.innerHTML = '';
  if (state.form) return renderCreateForm(ctx, root);
  if (!state.selected) {
    root.innerHTML = '<p class="placeholder">选择左侧节点查看详情</p>';
    return;
  }
  const { type, id } = state.selected;
  const obj = ctx.getObject(type, id);
  if (!obj) {
    root.innerHTML = '<p class="placeholder">数据未加载</p>';
    return;
  }
  if (state.editing) return renderEditForm(ctx, root, type, obj);
  renderView(ctx, root, type, obj);
}

/* ---------- 小工具 ---------- */

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function titleOf(type, obj) {
  return (type === 'experiment' || type === 'run') ? obj.name : `#${obj.seq_no}`;
}

function formatDateTime(value) {
  if (!value) return value;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
}

function fieldRow(dl, label, value) {
  dl.appendChild(el('dt', null, label));
  dl.appendChild(el('dd', null,
    value === null || value === undefined || value === '' ? '—' : String(value)));
}

function mdRow(dl, label, text) {
  dl.appendChild(el('dt', null, label));
  const dd = el('dd');
  if (text === null || text === undefined || text === '') dd.textContent = '—';
  else dd.appendChild(renderMarkdown(text));
  dl.appendChild(dd);
}

function chipList(dl, label, tags) {
  dl.appendChild(el('dt', null, label));
  const dd = el('dd');
  if (!tags || tags.length === 0) dd.textContent = '—';
  for (const t of tags || []) dd.appendChild(el('span', 'chip', t));
  dl.appendChild(dd);
}

function formShell(root, title, onSubmit) {
  root.appendChild(el('h2', null, title));
  const form = document.createElement('form');
  form.onsubmit = (e) => { e.preventDefault(); onSubmit(); };
  root.appendChild(form);
  return form;
}

function labeled(form, label, node) {
  const box = el('label', 'field');
  box.appendChild(el('span', null, label));
  box.appendChild(node);
  form.appendChild(box);
  return node;
}

function textInput(value = '') {
  const i = document.createElement('input');
  i.value = value ?? '';
  return i;
}

function textArea(value = '') {
  const t = document.createElement('textarea');
  t.value = value ?? '';
  return t;
}

function buttons(form, submitText, onCancel) {
  const bar = el('div', 'actions');
  const ok = el('button', 'primary', submitText);
  ok.type = 'submit';
  const cancel = el('button', null, '取消');
  cancel.type = 'button';
  cancel.onclick = onCancel;
  bar.appendChild(ok);
  bar.appendChild(cancel);
  form.appendChild(bar);
}

/* ---------- 标签编辑器（datalist 补全 + 回车成 chip） ---------- */

function tagEditor(initial) {
  const wrap = el('div', 'tag-editor');
  const values = [...(initial || [])];
  const chipsBox = el('div', 'chips');
  const input = document.createElement('input');
  input.setAttribute('list', 'tag-options');
  input.placeholder = '输入标签后回车';

  function renderChips() {
    chipsBox.innerHTML = '';
    values.forEach((t, i) => {
      const chip = el('span', 'chip', t);
      const x = el('button', 'chip-x', '×');
      x.type = 'button';
      x.onclick = () => { values.splice(i, 1); renderChips(); };
      chip.appendChild(x);
      chipsBox.appendChild(chip);
    });
  }
  input.onkeydown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = input.value.trim();
      if (v && !values.includes(v)) { values.push(v); renderChips(); }
      input.value = '';
    }
  };
  renderChips();
  wrap.appendChild(chipsBox);
  wrap.appendChild(input);
  return {
    el: wrap,
    get() {
      const pending = input.value.trim();
      if (pending && !values.includes(pending)) values.push(pending);
      return values;
    },
  };
}

/* ---------- 自变量定义编辑器（实验表单用） ---------- */

function varsEditor(initial) {
  const wrap = el('div', 'vars-editor');
  const rows = [];
  const addBtn = el('button', null, '＋ 添加自变量');
  addBtn.type = 'button';
  addBtn.onclick = () => addRow();
  wrap.appendChild(addBtn);

  function addRow(name = '', def = '') {
    const row = el('div', 'var-row');
    const nameI = textInput(name);
    nameI.placeholder = '名称（建议含单位，如 温度/℃）';
    const defI = textInput(def);
    defI.placeholder = '默认值';
    const rm = el('button', 'chip-x', '×');
    rm.type = 'button';
    rm.onclick = () => row.remove();
    row.append(nameI, defI, rm);
    row._get = () => ({ name: nameI.value.trim(), default: defI.value.trim() });
    rows.push(row);
    wrap.insertBefore(row, addBtn);
  }
  for (const v of initial || []) addRow(v.name, v.default);
  return {
    el: wrap,
    get: () => rows.filter(r => r.isConnected).map(r => r._get())
                   .filter(v => v.name),
  };
}

/* ---------- 详情查看 ---------- */

function renderView(ctx, root, type, obj) {
  root.appendChild(el('h2', null, `${ctx.LABEL[type]}：${titleOf(type, obj)}`));
  const dl = el('dl', 'fields');

  if (type === 'experiment') {
    fieldRow(dl, '目的', obj.purpose);
    fieldRow(dl, '方法', obj.method);
    fieldRow(dl, '自变量', (obj.independent_vars || [])
      .map(v => `${v.name}（默认 ${v.default || '—'}）`).join('；'));
    fieldRow(dl, '因变量', (obj.dependent_vars || []).join('；'));
    chipList(dl, '分类标签', obj.category_tags);
    mdRow(dl, '结论', obj.conclusion);
    chipList(dl, '评价标签', obj.evaluation_tags);
    fieldRow(dl, '创建时间', formatDateTime(obj.created_at));
    fieldRow(dl, '更新时间', formatDateTime(obj.updated_at));
  } else if (type === 'run') {
    fieldRow(dl, '名称', obj.name);
    mdRow(dl, '摘要', obj.summary);
    chipList(dl, '评价标签', obj.evaluation_tags);
    fieldRow(dl, '创建时间', formatDateTime(obj.created_at));
  } else if (type === 'group') {
    fieldRow(dl, '序号', '#' + obj.seq_no);
    fieldRow(dl, '自变量取值', Object.entries(obj.variable_values || {})
      .map(([k, v]) => `${k} = ${v}`).join('；'));
    mdRow(dl, '摘要', obj.summary);
    chipList(dl, '评价标签', obj.evaluation_tags);
    fieldRow(dl, '创建时间', formatDateTime(obj.created_at));
  } else {
    fieldRow(dl, '编号', '#' + obj.seq_no);
    fieldRow(dl, '开始时间', formatDateTime(obj.started_at));
    fieldRow(dl, '数据目录', obj.data_path);
    mdRow(dl, '测试结果', obj.summary);
    chipList(dl, '评价标签', obj.evaluation_tags);
  }
  root.appendChild(dl);

  root.appendChild(attachmentSection(ctx, type, obj, async () => {
    // Attempt 的数据内嵌在其 Group 详情里，必须刷新 Group 才能拿到新附件列表
    if (type === 'attempt') {
      await ctx.fetchDetail('group', obj.group_id, true);
      await ctx.refreshAll();
      await ctx.select('attempt', obj.id);
    } else {
      ctx.state.details.delete(ctx.key(type, obj.id));
      await ctx.refreshAll();
      await ctx.select(type, obj.id);
    }
  }));

  const bar = el('div', 'actions');
  if (type === 'group') {
    const btn = el('button', 'primary', '＋ 新建 Attempt');
    btn.onclick = () => createAttempt(ctx, obj.id);
    bar.appendChild(btn);
  } else if (type === 'experiment' || type === 'run') {
    const childType = type === 'experiment' ? 'run' : 'group';
    const btn = el('button', 'primary',
      `＋ 新建 ${childType === 'run' ? 'Run' : 'Group'}`);
    btn.onclick = () => {
      ctx.state.form = { type: childType, parentId: obj.id };
      ctx.renderAll();
    };
    bar.appendChild(btn);
  }
  const edit = el('button', null, '编辑');
  edit.onclick = () => { ctx.state.editing = true; ctx.renderAll(); };
  bar.appendChild(edit);
  const del = el('button', 'danger', '删除');
  del.onclick = () => confirmDelete(ctx, type, obj);
  bar.appendChild(del);
  root.appendChild(bar);
}

/* ---------- 保存后的统一收尾 ---------- */

async function commitAndShow(ctx, type, id) {
  ctx.state.form = null;
  ctx.state.editing = false;
  ctx.state.details.delete(ctx.key(type, id));
  await ctx.refreshAll();
  await ctx.select(type, id);
}

async function commitAndShowAttempt(ctx, attempt) {
  ctx.state.form = null;
  ctx.state.editing = false;
  await ctx.fetchDetail('group', attempt.group_id, true);
  ctx.state.expanded.add(ctx.key('group', attempt.group_id));
  await ctx.refreshAll();
  await ctx.select('attempt', attempt.id);
}

/* ---------- 表单：创建与编辑 ---------- */

function renderCreateForm(ctx, root) {
  const { type, parentId } = ctx.state.form;
  if (type === 'experiment') return experimentForm(ctx, root, null);
  if (type === 'run') return runForm(ctx, root, parentId, null);
  if (type === 'group') groupCreateForm(ctx, root, parentId);
}

function renderEditForm(ctx, root, type, obj) {
  if (type === 'experiment') return experimentForm(ctx, root, obj);
  if (type === 'run') return runForm(ctx, root, null, obj);
  if (type === 'group') return groupEditForm(ctx, root, obj);
  return attemptEditForm(ctx, root, obj);
}

function cancelForm(ctx) {
  ctx.state.form = null;
  ctx.state.editing = false;
  ctx.renderAll();
}

function experimentForm(ctx, root, obj) {
  const creating = !obj;
  const form = formShell(root, creating ? '新建实验' : '编辑实验', submit);
  const name = labeled(form, '名称 *', textInput(obj ? obj.name : ''));
  const purpose = labeled(form, '目的', textArea(obj ? obj.purpose : ''));
  const method = labeled(form, '方法', textArea(obj ? obj.method : ''));
  const vars = varsEditor(obj ? obj.independent_vars : []);
  labeled(form, '自变量（名称 + 默认值）', vars.el);
  const dep = labeled(form, '因变量（逗号分隔）',
    textInput(obj ? (obj.dependent_vars || []).join(', ') : ''));
  const cat = tagEditor(obj ? obj.category_tags : []);
  labeled(form, '分类标签', cat.el);
  let conclusion, evalTags;
  if (!creating) {
    conclusion = markdownField('结论', obj.conclusion, 'experiment', obj.id,
                               ctx.showToast);
    form.appendChild(conclusion.el);
    evalTags = tagEditor(obj.evaluation_tags);
    labeled(form, '评价标签', evalTags.el);
  }
  buttons(form, creating ? '创建' : '保存', () => cancelForm(ctx));

  async function submit() {
    const body = {
      name: name.value.trim(),
      purpose: purpose.value,
      method: method.value,
      independent_vars: vars.get(),
      dependent_vars: dep.value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
      category_tags: cat.get(),
    };
    if (!creating) {
      body.conclusion = conclusion.get();
      body.evaluation_tags = evalTags.get();
    }
    try {
      const saved = creating
        ? await API.post('/experiments', body)
        : await API.patch('/experiments/' + obj.id, body);
      await commitAndShow(ctx, 'experiment', saved.id);
    } catch (err) { ctx.showToast(err.message); }
  }
}

function runForm(ctx, root, parentId, obj) {
  const creating = !obj;
  const form = formShell(root, creating ? '新建 Run' : '编辑 Run', submit);
  const name = labeled(form, '名称 *', textInput(obj ? obj.name : ''));
  let summary, evalTags;
  if (!creating) {
    summary = markdownField('摘要', obj.summary, 'run', obj.id, ctx.showToast);
    form.appendChild(summary.el);
    evalTags = tagEditor(obj.evaluation_tags);
    labeled(form, '评价标签', evalTags.el);
  }
  buttons(form, creating ? '创建' : '保存', () => cancelForm(ctx));

  async function submit() {
    try {
      let saved;
      if (creating) {
        saved = await API.post(`/experiments/${parentId}/runs`,
                               { name: name.value.trim() });
        ctx.state.expanded.add(ctx.key('experiment', parentId));
      } else {
        saved = await API.patch('/runs/' + obj.id, {
          name: name.value.trim(),
          summary: summary.get(),
          evaluation_tags: evalTags.get(),
        });
      }
      await commitAndShow(ctx, 'run', saved.id);
    } catch (err) { ctx.showToast(err.message); }
  }
}

async function groupCreateForm(ctx, root, parentId) {
  let tpl;
  try {
    tpl = await API.get(`/runs/${parentId}/new-group-template`);
  } catch (err) { ctx.showToast(err.message); return; }
  const form = formShell(root, '新建 Group（已预填实验默认条件）', submit);
  const rows = Object.entries(tpl.variable_values).map(([k, v]) => {
    const input = textInput(v);
    labeled(form, k, input);
    return [k, input];
  });
  if (rows.length === 0) form.appendChild(
    el('p', 'placeholder', '该实验未定义自变量，可直接创建'));
  buttons(form, '创建', () => cancelForm(ctx));

  async function submit() {
    const vv = {};
    for (const [k, input] of rows) vv[k] = input.value;
    try {
      const saved = await API.post(`/runs/${parentId}/groups`,
                                   { variable_values: vv });
      ctx.state.expanded.add(ctx.key('run', parentId));
      await commitAndShow(ctx, 'group', saved.id);
    } catch (err) { ctx.showToast(err.message); }
  }
}

function groupEditForm(ctx, root, obj) {
  const form = formShell(root, `编辑 Group #${obj.seq_no}`, submit);
  const rows = Object.entries(obj.variable_values || {}).map(([k, v]) => {
    const input = textInput(v);
    labeled(form, k, input);
    return [k, input];
  });
  const summary = markdownField('摘要（综合各 Attempt 的结果）', obj.summary,
                                'group', obj.id, ctx.showToast);
  form.appendChild(summary.el);
  const evalTags = tagEditor(obj.evaluation_tags);
  labeled(form, '评价标签', evalTags.el);
  buttons(form, '保存', () => cancelForm(ctx));

  async function submit() {
    const vv = {};
    for (const [k, input] of rows) vv[k] = input.value;
    try {
      await API.patch('/groups/' + obj.id, {
        variable_values: vv,
        summary: summary.get(),
        evaluation_tags: evalTags.get(),
      });
      await commitAndShow(ctx, 'group', obj.id);
    } catch (err) { ctx.showToast(err.message); }
  }
}

function attemptEditForm(ctx, root, obj) {
  const form = formShell(root, `编辑 Attempt #${obj.seq_no}`, submit);
  const dataPath = labeled(form,
    '数据保存目录（大体积原始数据放这里，应用只记路径）', textInput(obj.data_path));
  const summary = markdownField('测试结果（支持 Markdown，可直接粘贴截图）',
                                obj.summary, 'attempt', obj.id, ctx.showToast);
  form.appendChild(summary.el);
  const evalTags = tagEditor(obj.evaluation_tags);
  labeled(form, '评价标签', evalTags.el);
  buttons(form, '保存', () => cancelForm(ctx));

  async function submit() {
    try {
      const saved = await API.patch('/attempts/' + obj.id, {
        data_path: dataPath.value,
        summary: summary.get(),
        evaluation_tags: evalTags.get(),
      });
      await commitAndShowAttempt(ctx, saved);
    } catch (err) { ctx.showToast(err.message); }
  }
}

/* ---------- 新建 Attempt（一键，无表单） ---------- */

async function createAttempt(ctx, groupId) {
  try {
    const saved = await API.post(`/groups/${groupId}/attempts`);
    await commitAndShowAttempt(ctx, saved);
  } catch (err) { ctx.showToast(err.message); }
}

/* ---------- 删除（先统计后代数量再确认） ---------- */

async function confirmDelete(ctx, type, obj) {
  try {
    const counts = { run: 0, group: 0, attempt: 0 };
    await countDescendants(ctx, type, obj.id, counts);
    const parts = [];
    if (counts.run) parts.push(`${counts.run} 个 Run`);
    if (counts.group) parts.push(`${counts.group} 个 Group`);
    if (counts.attempt) parts.push(`${counts.attempt} 个 Attempt`);
    const extra = parts.length ? `\n将连带删除：${parts.join('、')}。` : '';
    const name = titleOf(type, obj);
    if (!window.confirm(
      `确定删除 ${ctx.LABEL[type]}「${name}」吗？${extra}\n此操作不可恢复。`)) return;
    await API.del(DEL_PATH[type] + obj.id);
    ctx.state.selected = null;
    ctx.state.details.delete(ctx.key(type, obj.id));
    ctx.state.expanded.delete(ctx.key(type, obj.id));
    await ctx.refreshAll();
  } catch (err) { ctx.showToast(err.message); }
}

async function countDescendants(ctx, type, id, counts) {
  if (type === 'attempt') return;
  const detail = await ctx.fetchDetail(type, id, true);
  if (type === 'experiment') {
    counts.run += detail.runs.length;
    for (const r of detail.runs) await countDescendants(ctx, 'run', r.id, counts);
  } else if (type === 'run') {
    counts.group += detail.groups.length;
    for (const g of detail.groups) counts.attempt += g.attempt_count;
  } else if (type === 'group') {
    counts.attempt += detail.attempts.length;
  }
}
