import API from './api.js';
import { markdownField, markdownSummary, renderMarkdown } from './markdown.js';
import { attachmentSection } from './attachments.js';
import { openLightbox } from './lightbox.js';

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
  const { id } = state.selected;
  const obj = ctx.getObject('experiment', id);
  if (!obj) {
    root.innerHTML = '<p class="placeholder">数据未加载</p>';
    return;
  }
  if (state.editing) return experimentForm(ctx, root, obj);
  renderExperimentView(ctx, root, obj);
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
  return bar;
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

function resultEditor(initial) {
  const wrap = el('div', 'result-editor');
  const rows = [];
  const addBtn = el('button', null, '＋ 添加测试结果');
  addBtn.type = 'button';
  addBtn.onclick = () => addRow();
  wrap.appendChild(addBtn);

  function addRow(name = '', value = '') {
    const row = el('div', 'result-row');
    const nameInput = textInput(name);
    nameInput.placeholder = '因变量名称';
    const valueInput = textInput(value);
    valueInput.placeholder = '测试值';
    const remove = el('button', 'chip-x', '×');
    remove.type = 'button';
    remove.setAttribute('aria-label', '删除测试结果');
    remove.onclick = () => row.remove();
    row.append(nameInput, valueInput, remove);
    row._get = () => ({
      name: nameInput.value.trim(),
      value: valueInput.value,
    });
    rows.push(row);
    wrap.insertBefore(row, addBtn);
  }

  for (const result of initial || []) addRow(result.name, result.value);
  return {
    el: wrap,
    get: () => rows.filter(row => row.isConnected).map(row => row._get())
      .filter(result => result.name),
  };
}

function resultTable(results) {
  const table = el('table', 'result-table');
  const tbody = document.createElement('tbody');
  for (const result of results || []) {
    const row = document.createElement('tr');
    row.append(el('th', null, result.name),
               el('td', null, result.value || '—'));
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  return table;
}

/* ---------- 详情查看 ---------- */

function renderExperimentView(ctx, root, obj) {
  root.appendChild(el('h2', null, `实验：${obj.name}`));
  const dl = el('dl', 'fields');
  fieldRow(dl, '目的', obj.purpose);
  mdRow(dl, '方法', obj.method);
  fieldRow(dl, '自变量', (obj.independent_vars || [])
    .map(v => `${v.name}（默认 ${v.default || '—'}）`).join('；'));
  fieldRow(dl, '因变量', (obj.dependent_vars || []).join('；'));
  chipList(dl, '分类标签', obj.category_tags);
  mdRow(dl, '结论', obj.conclusion);
  chipList(dl, '评价标签', obj.evaluation_tags);
  fieldRow(dl, '创建时间', formatDateTime(obj.created_at));
  fieldRow(dl, '更新时间', formatDateTime(obj.updated_at));
  root.appendChild(dl);

  const bar = el('div', 'actions');
  const create = el('button', 'primary', '＋ 新建 Attempt');
  create.onclick = () => ctx.openDrawer({ kind: 'new-attempt', experimentId: obj.id });
  bar.appendChild(create);
  const edit = el('button', null, '编辑');
  edit.onclick = () => { ctx.state.editing = true; ctx.renderAll(); };
  bar.appendChild(edit);
  const del = el('button', 'danger', '删除');
  del.onclick = () => confirmDelete(ctx, 'experiment', obj);
  bar.appendChild(del);
  root.appendChild(bar);

  renderAttemptOverview(ctx, root, obj.id);
}

function groupDescription(group) {
  const values = Object.entries(group.variable_values || {})
    .map(([name, value]) => `${name}=${value}`).join(', ');
  return `Group #${group.seq_no}${values ? `（${values}）` : ''}`;
}

function renderAttemptOverview(ctx, root, experimentId) {
  const section = el('section', 'attempt-overview');
  section.appendChild(el('h3', null, 'Attempts'));
  const overview = ctx.state.overviews.get(experimentId);
  if (!overview) {
    section.appendChild(el('p', 'placeholder', '正在加载 Attempt…'));
    root.appendChild(section);
    return;
  }

  const selected = ctx.state.comboFilters.get(experimentId) || new Set();
  const picker = document.createElement('details');
  picker.className = 'combo-picker';
  const pickerSummary = document.createElement('summary');
  picker.appendChild(pickerSummary);
  const menu = el('div', 'combo-menu');
  const menuActions = el('div', 'combo-menu-actions');
  const selectAll = el('button', null, '全选');
  selectAll.type = 'button';
  const clearAll = el('button', null, '清空');
  clearAll.type = 'button';
  menuActions.append(selectAll, clearAll);
  menu.appendChild(menuActions);
  const checkboxes = [];

  let lastRunId = null;
  for (const combo of overview.combinations) {
    if (combo.run.id !== lastRunId) {
      menu.appendChild(el('div', 'combo-run-name', combo.run.name));
      lastRunId = combo.run.id;
    }
    const label = el('label', 'combo-option');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selected.has(combo.key);
    checkbox.onchange = () => {
      checkbox.checked ? selected.add(combo.key) : selected.delete(combo.key);
      updateSummary();
      renderCards();
    };
    label.append(checkbox, document.createTextNode(groupDescription(combo.group)));
    menu.appendChild(label);
    checkboxes.push({ checkbox, key: combo.key });
  }
  picker.appendChild(menu);
  section.appendChild(picker);

  const cards = el('div', 'attempt-cards');
  section.appendChild(cards);
  root.appendChild(section);

  function updateSummary() {
    pickerSummary.textContent = overview.combinations.length
      ? `筛选 Run / Group（已选 ${selected.size}/${overview.combinations.length}）`
      : '筛选 Run / Group（暂无组合）';
  }

  function setAll(checked) {
    for (const item of checkboxes) {
      item.checkbox.checked = checked;
      checked ? selected.add(item.key) : selected.delete(item.key);
    }
    updateSummary();
    renderCards();
  }

  selectAll.onclick = () => setAll(true);
  clearAll.onclick = () => setAll(false);

  function renderCards() {
    cards.innerHTML = '';
    const visible = overview.attempts
      .filter(item => selected.has(item.comboKey))
      .sort((a, b) => new Date(b.attempt.started_at) - new Date(a.attempt.started_at)
        || b.attempt.id - a.attempt.id);
    if (visible.length === 0) {
      const message = overview.combinations.length && selected.size === 0
        ? '请至少选择一个 Run / Group 组合'
        : '所选组合中暂无 Attempt';
      cards.appendChild(el('p', 'placeholder', message));
      return;
    }
    for (const item of visible) cards.appendChild(attemptCard(ctx, item));
  }

  updateSummary();
  renderCards();
}

function attemptCard(ctx, item) {
  const { attempt, run, group } = item;
  const card = el('article', 'attempt-card');
  card.tabIndex = 0;
  card.setAttribute('role', 'button');
  card.appendChild(el('h4', null,
    `${run.name} / Group #${group.seq_no} / Attempt #${attempt.seq_no}`));
  const meta = el('div', 'attempt-card-meta');
  meta.appendChild(el('time', null, formatDateTime(attempt.started_at)));
  for (const tag of attempt.evaluation_tags || []) {
    meta.appendChild(el('span', 'chip chip-eval', tag));
  }
  card.appendChild(meta);

  const results = el('section', 'attempt-card-results');
  results.appendChild(el('h5', null, '测试结果'));
  if (attempt.results?.length) results.appendChild(resultTable(attempt.results));
  else results.appendChild(el('p', 'placeholder', '暂无测试结果'));
  card.appendChild(results);

  const description = markdownSummary(attempt.description);
  card.appendChild(el('p', description.text ? 'attempt-excerpt' : 'attempt-excerpt placeholder',
    description.text || '暂无说明'));
  if (description.images.length) {
    const gallery = el('div', 'attempt-thumbnails');
    description.images.forEach((image, index) => {
      const button = el('button', 'attempt-thumbnail');
      button.type = 'button';
      button.setAttribute('aria-label', `查看插图 ${index + 1}`);
      const img = document.createElement('img');
      img.src = image.src;
      img.alt = image.alt || `Attempt 插图 ${index + 1}`;
      button.appendChild(img);
      button.onclick = event => {
        event.stopPropagation();
        openLightbox(description.images, index);
      };
      gallery.appendChild(button);
    });
    card.appendChild(gallery);
  }

  const openBody = () => ctx.openDrawer({ kind: 'attempt-view', id: attempt.id });
  card.onclick = openBody;
  card.onkeydown = event => {
    if (event.target === card && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      openBody();
    }
  };
  return card;
}

function attemptContext(ctx, attemptId) {
  for (const overview of ctx.state.overviews.values()) {
    const hit = overview.attempts.find(item => item.attempt.id === attemptId);
    if (hit) return hit;
  }
  const attempt = ctx.getObject('attempt', attemptId);
  return attempt ? { attempt, run: null, group: null } : null;
}

export function renderDrawer(ctx) {
  const drawer = document.getElementById('drawer');
  const backdrop = document.getElementById('drawer-backdrop');
  const root = document.getElementById('drawer-content');
  root.innerHTML = '';
  const state = ctx.state.drawer;
  drawer.classList.toggle('hidden', !state);
  backdrop.classList.toggle('hidden', !state);
  if (!state) return;

  if (state.kind === 'attempt-view') {
    return renderAttemptBodyDrawer(ctx, root, state.id);
  }
  if (state.kind === 'new-attempt') {
    const experiment = ctx.getObject('experiment', state.experimentId);
    if (experiment) return newAttemptDrawer(ctx, root, experiment);
  }
  if (state.kind === 'edit') {
    const obj = ctx.getObject(state.type, state.id);
    if (!obj) {
      root.appendChild(el('p', 'placeholder', '数据未加载'));
      return;
    }
    if (state.type === 'run') return runForm(ctx, root, obj);
    if (state.type === 'group') return groupEditForm(ctx, root, obj);
    if (state.type === 'attempt') return attemptEditForm(ctx, root, obj);
  }
  root.appendChild(el('p', 'placeholder', '无法打开侧边栏内容'));
}

function renderAttemptBodyDrawer(ctx, root, attemptId) {
  const item = attemptContext(ctx, attemptId);
  if (!item) {
    root.appendChild(el('p', 'placeholder', 'Attempt 数据未加载'));
    return;
  }
  const { attempt, run, group } = item;
  const title = run && group
    ? `${run.name} / Group #${group.seq_no} / Attempt #${attempt.seq_no}`
    : `Attempt #${attempt.seq_no}`;
  root.appendChild(el('h2', null, title));
  const meta = el('div', 'drawer-meta');
  meta.appendChild(el('time', null, formatDateTime(attempt.started_at)));
  for (const tag of attempt.evaluation_tags || []) {
    meta.appendChild(el('span', 'chip chip-eval', tag));
  }
  root.appendChild(meta);
  root.appendChild(el('h3', null, '测试结果'));
  if (attempt.results?.length) root.appendChild(resultTable(attempt.results));
  else root.appendChild(el('p', 'placeholder', '暂无测试结果'));
  root.appendChild(el('h3', 'drawer-section-title', '说明'));
  const body = el('section', 'attempt-body');
  body.appendChild(renderMarkdown(attempt.description || ''));
  if (!attempt.description) body.appendChild(el('p', 'placeholder', '暂无说明'));
  root.appendChild(body);
  const bar = el('div', 'actions');
  const edit = el('button', 'primary', '编辑 Attempt');
  edit.onclick = () => ctx.openDrawer({ kind: 'edit', type: 'attempt', id: attempt.id });
  bar.appendChild(edit);
  root.appendChild(bar);
}

function newAttemptDrawer(ctx, root, experiment) {
  const overview = ctx.state.overviews.get(experiment.id) ||
    { runs: [], combinations: [], attempts: [] };
  const form = formShell(root, '新建 Attempt', submit);

  const runSelect = document.createElement('select');
  for (const run of overview.runs) {
    const option = document.createElement('option');
    option.value = String(run.id);
    option.textContent = run.name;
    runSelect.appendChild(option);
  }
  const newRunOption = document.createElement('option');
  newRunOption.value = '__new__';
  newRunOption.textContent = '＋ 新建 Run';
  runSelect.appendChild(newRunOption);
  if (runSelect.options.length === 1) runSelect.value = '__new__';
  labeled(form, 'Run', runSelect);

  const runName = textInput();
  runName.placeholder = '新 Run 名称';
  labeled(form, '新 Run 名称 *', runName);
  const runNameField = runName.closest('.field');

  const groupSelect = document.createElement('select');
  labeled(form, 'Group', groupSelect);
  const groupField = groupSelect.closest('.field');

  const variableBox = el('div', 'new-group-fields');
  const variableRows = (experiment.independent_vars || []).map(variable => {
    const input = textInput(variable.default || '');
    labeled(variableBox, variable.name, input);
    return [variable.name, input];
  });
  if (variableRows.length === 0) {
    variableBox.appendChild(el('p', 'placeholder', '该实验未定义自变量'));
  }
  form.appendChild(variableBox);

  runSelect.onchange = updateChoices;
  groupSelect.onchange = updateVariableVisibility;
  updateChoices();
  const actionBar = buttons(form, '创建 Attempt', () => ctx.closeDrawer());

  function updateChoices() {
    const creatingRun = runSelect.value === '__new__';
    runNameField.classList.toggle('hidden', !creatingRun);
    groupField.classList.toggle('hidden', creatingRun);
    groupSelect.innerHTML = '';
    if (!creatingRun) {
      const runId = Number(runSelect.value);
      for (const combo of overview.combinations.filter(item => item.run.id === runId)) {
        const option = document.createElement('option');
        option.value = String(combo.group.id);
        option.textContent = groupDescription(combo.group);
        groupSelect.appendChild(option);
      }
      const option = document.createElement('option');
      option.value = '__new__';
      option.textContent = '＋ 新建 Group';
      groupSelect.appendChild(option);
      if (groupSelect.options.length === 1) groupSelect.value = '__new__';
    }
    updateVariableVisibility();
  }

  function updateVariableVisibility() {
    const creatingGroup = runSelect.value === '__new__' ||
      groupSelect.value === '__new__';
    variableBox.classList.toggle('hidden', !creatingGroup);
  }

  async function submit() {
    const submitButton = actionBar.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      let runId;
      if (runSelect.value === '__new__') {
        const run = await API.post(`/experiments/${experiment.id}/runs`, {
          name: runName.value.trim(),
        });
        runId = run.id;
        ctx.state.expanded.add(ctx.key('experiment', experiment.id));
      } else {
        runId = Number(runSelect.value);
      }

      let groupId;
      if (runSelect.value === '__new__' || groupSelect.value === '__new__') {
        const variableValues = {};
        for (const [name, input] of variableRows) variableValues[name] = input.value;
        const group = await API.post(`/runs/${runId}/groups`, {
          variable_values: variableValues,
        });
        groupId = group.id;
        ctx.state.expanded.add(ctx.key('run', runId));
      } else {
        groupId = Number(groupSelect.value);
      }

      const attempt = await API.post(`/groups/${groupId}/attempts`);
      ctx.state.expanded.add(ctx.key('experiment', experiment.id));
      ctx.state.expanded.add(ctx.key('run', runId));
      ctx.state.expanded.add(ctx.key('group', groupId));
      const comboKey = `${runId}:${groupId}`;
      if (!ctx.state.comboFilters.has(experiment.id)) {
        ctx.state.comboFilters.set(experiment.id, new Set());
      }
      ctx.state.comboFilters.get(experiment.id).add(comboKey);
      ctx.state.drawer = { kind: 'edit', type: 'attempt', id: attempt.id };
      await ctx.refreshAll();
    } catch (err) {
      ctx.showToast(err.message);
      submitButton.disabled = false;
    }
  }
}

/* ---------- 保存后的统一收尾 ---------- */

async function commitAndShow(ctx, type, id) {
  ctx.state.form = null;
  ctx.state.editing = false;
  ctx.state.details.delete(ctx.key(type, id));
  await ctx.refreshAll();
  await ctx.select(type, id);
}

async function finishDrawerEdit(ctx, type, obj) {
  ctx.state.drawer = null;
  ctx.state.details.delete(ctx.key(type, obj.id));
  if (type === 'attempt') {
    await ctx.fetchDetail('group', obj.group_id, true);
  }
  await ctx.refreshAll();
}

function addDrawerDelete(ctx, bar, type, obj) {
  const del = el('button', 'danger', '删除');
  del.type = 'button';
  del.onclick = () => confirmDelete(ctx, type, obj, true);
  bar.appendChild(del);
}

/* ---------- 表单：创建与编辑 ---------- */

function renderCreateForm(ctx, root) {
  if (ctx.state.form.type === 'experiment') return experimentForm(ctx, root, null);
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
  const method = markdownField(
    creating ? '方法（支持 Markdown；创建后可粘贴图片）'
      : '方法（支持 Markdown，可直接粘贴图片）',
    obj ? obj.method : '', creating ? null : 'experiment',
    obj ? obj.id : null, ctx.showToast);
  form.appendChild(method.el);
  const vars = varsEditor(obj ? obj.independent_vars : []);
  labeled(form, '自变量（名称 + 默认值）', vars.el);
  const dep = labeled(form, '因变量（逗号分隔）',
    textInput(obj ? (obj.dependent_vars || []).join(', ') : ''));
  const cat = tagEditor(obj ? obj.category_tags : []);
  labeled(form, '分类标签', cat.el);
  let conclusion, evalTags;
  if (!creating) {
    conclusion = markdownField('结论（支持 Markdown，可直接粘贴图片）',
                               obj.conclusion, 'experiment', obj.id,
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
      method: method.get(),
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

function runForm(ctx, root, obj) {
  const form = formShell(root, '编辑 Run', submit);
  const name = labeled(form, '名称 *', textInput(obj.name));
  const summary = markdownField('摘要（支持 Markdown，可直接粘贴图片）',
                                obj.summary, 'run', obj.id, ctx.showToast);
  form.appendChild(summary.el);
  const evalTags = tagEditor(obj.evaluation_tags);
  labeled(form, '评价标签', evalTags.el);
  const bar = buttons(form, '保存', () => ctx.closeDrawer());
  addDrawerDelete(ctx, bar, 'run', obj);

  async function submit() {
    try {
      const saved = await API.patch('/runs/' + obj.id, {
        name: name.value.trim(),
        summary: summary.get(),
        evaluation_tags: evalTags.get(),
      });
      await finishDrawerEdit(ctx, 'run', saved);
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
  const bar = buttons(form, '保存', () => ctx.closeDrawer());
  addDrawerDelete(ctx, bar, 'group', obj);

  async function submit() {
    const vv = {};
    for (const [k, input] of rows) vv[k] = input.value;
    try {
      await API.patch('/groups/' + obj.id, {
        variable_values: vv,
      });
      await finishDrawerEdit(ctx, 'group', obj);
    } catch (err) { ctx.showToast(err.message); }
  }
}

function attemptEditForm(ctx, root, obj) {
  const form = formShell(root, `编辑 Attempt #${obj.seq_no}`, submit);
  const dataPath = labeled(form,
    '数据保存目录（大体积原始数据放这里，应用只记路径）', textInput(obj.data_path));
  const results = resultEditor(obj.results);
  labeled(form, '测试结果（因变量名称 + 测试值）', results.el);
  const description = markdownField('说明（支持 Markdown，可直接粘贴截图）',
                                    obj.description, 'attempt', obj.id,
                                    ctx.showToast);
  form.appendChild(description.el);
  const evalTags = tagEditor(obj.evaluation_tags);
  labeled(form, '评价标签', evalTags.el);
  const bar = buttons(form, '保存', () => ctx.closeDrawer());
  addDrawerDelete(ctx, bar, 'attempt', obj);
  root.appendChild(attachmentSection(ctx, 'attempt', obj, async () => {
    await ctx.fetchDetail('group', obj.group_id, true);
    await ctx.refreshAll();
    ctx.state.drawer = { kind: 'edit', type: 'attempt', id: obj.id };
    ctx.renderAll();
  }));

  async function submit() {
    try {
      const saved = await API.patch('/attempts/' + obj.id, {
        data_path: dataPath.value,
        results: results.get(),
        description: description.get(),
        evaluation_tags: evalTags.get(),
      });
      await finishDrawerEdit(ctx, 'attempt', saved);
    } catch (err) { ctx.showToast(err.message); }
  }
}

/* ---------- 删除（先统计后代数量再确认） ---------- */

async function confirmDelete(ctx, type, obj, preserveExperiment = false) {
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
    if (!preserveExperiment || type === 'experiment') ctx.state.selected = null;
    ctx.state.drawer = null;
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
