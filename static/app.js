import API from './api.js';
import { renderDetail } from './detail.js';

export const state = {
  experiments: [],
  details: new Map(),   // "run:3" -> 详情对象（含内嵌子级列表）
  expanded: new Set(),  // "experiment:1"
  selected: null,       // {type, id} | null
  filterTags: new Set(),
  allTags: [],
  form: null,           // {type, parentId} 创建表单状态
  editing: false,
};

export const LABEL = { experiment: '实验', run: 'Run', group: 'Group', attempt: 'Attempt' };
const DETAIL_PATH = { experiment: '/experiments/', run: '/runs/', group: '/groups/' };
const CHILD_LIST = { experiment: 'runs', run: 'groups', group: 'attempts' };
const CHILD_TYPE = { experiment: 'run', run: 'group', group: 'attempt' };

export function key(type, id) { return `${type}:${id}`; }

export function showToast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add('hidden'), 5000);
}

export async function loadExperiments() {
  state.experiments = (await API.get('/experiments')).experiments;
}

export async function loadTags() {
  state.allTags = (await API.get('/tags')).tags;
  const dl = document.getElementById('tag-options');
  dl.innerHTML = '';
  for (const t of state.allTags) {
    const opt = document.createElement('option');
    opt.value = t;
    dl.appendChild(opt);
  }
}

export async function fetchDetail(type, id, force = false) {
  const k = key(type, id);
  if (!force && state.details.has(k)) return state.details.get(k);
  const obj = await API.get(DETAIL_PATH[type] + id);
  state.details.set(k, obj);
  return obj;
}

export function getObject(type, id) {
  // attempt 没有独立 GET，数据在其所属 group 的详情里
  if (type === 'attempt') {
    for (const [k, v] of state.details) {
      if (k.startsWith('group:')) {
        const hit = (v.attempts || []).find(a => a.id === id);
        if (hit) return hit;
      }
    }
    return null;
  }
  return state.details.get(key(type, id)) ||
    (type === 'experiment' ? state.experiments.find(e => e.id === id) : null);
}

function nodeTitle(type, obj) {
  if (type === 'experiment' || type === 'run') return obj.name;
  if (type === 'group') {
    const vars = Object.entries(obj.variable_values || {})
      .map(([k, v]) => `${k}=${v}`).join(', ');
    return `Group #${obj.seq_no}${vars ? '（' + vars + '）' : ''}`;
  }
  return `Attempt #${obj.seq_no}`;
}

function renderFilter() {
  const box = document.getElementById('tag-filter');
  box.innerHTML = '';
  const inUse = new Set();
  for (const e of state.experiments)
    for (const t of [...(e.category_tags || []), ...(e.evaluation_tags || [])])
      inUse.add(t);
  for (const t of [...inUse].sort()) {
    const chip = document.createElement('button');
    chip.className = 'chip chip-filter' + (state.filterTags.has(t) ? ' active' : '');
    chip.textContent = t;
    chip.onclick = () => {
      state.filterTags.has(t) ? state.filterTags.delete(t) : state.filterTags.add(t);
      renderFilter();
      renderTree();
    };
    box.appendChild(chip);
  }
}

function renderTree() {
  const root = document.getElementById('tree');
  root.innerHTML = '';
  const visible = state.experiments.filter(e => {
    if (state.filterTags.size === 0) return true;
    const tags = [...(e.category_tags || []), ...(e.evaluation_tags || [])];
    return [...state.filterTags].every(t => tags.includes(t));
  });
  if (visible.length === 0) {
    root.innerHTML = '<p class="placeholder">暂无实验</p>';
    return;
  }
  const ul = document.createElement('ul');
  for (const exp of visible) ul.appendChild(renderNode('experiment', exp));
  root.appendChild(ul);
}

function renderNode(type, obj) {
  const li = document.createElement('li');
  const row = document.createElement('div');
  const isSel = state.selected &&
    state.selected.type === type && state.selected.id === obj.id;
  row.className = 'node' + (isSel ? ' selected' : '');

  if (type !== 'attempt') {
    const btn = document.createElement('button');
    btn.className = 'expander';
    btn.textContent = state.expanded.has(key(type, obj.id)) ? '▾' : '▸';
    btn.onclick = (e) => { e.stopPropagation(); toggleExpand(type, obj.id); };
    row.appendChild(btn);
  } else {
    const spacer = document.createElement('span');
    spacer.className = 'expander-spacer';
    row.appendChild(spacer);
  }

  const label = document.createElement('span');
  label.className = 'node-label';
  label.textContent = nodeTitle(type, obj);
  row.appendChild(label);

  for (const t of obj.evaluation_tags || []) {
    const chip = document.createElement('span');
    chip.className = 'chip chip-eval';
    chip.textContent = t;
    row.appendChild(chip);
  }
  row.onclick = () => select(type, obj.id);
  li.appendChild(row);

  if (type !== 'attempt' && state.expanded.has(key(type, obj.id))) {
    const detail = state.details.get(key(type, obj.id));
    const children = detail ? (detail[CHILD_LIST[type]] || []) : [];
    const ul = document.createElement('ul');
    if (children.length === 0) {
      const empty = document.createElement('li');
      empty.className = 'placeholder';
      empty.textContent = '（空）';
      ul.appendChild(empty);
    }
    for (const c of children) ul.appendChild(renderNode(CHILD_TYPE[type], c));
    li.appendChild(ul);
  }
  return li;
}

export async function toggleExpand(type, id) {
  const k = key(type, id);
  try {
    if (state.expanded.has(k)) {
      state.expanded.delete(k);
    } else {
      await fetchDetail(type, id);
      state.expanded.add(k);
    }
    renderAll();
  } catch (err) { showToast(err.message); }
}

export async function select(type, id) {
  try {
    state.selected = { type, id };
    state.form = null;
    state.editing = false;
    if (type !== 'attempt') await fetchDetail(type, id);
    renderAll();
  } catch (err) { showToast(err.message); }
}

export function renderAll() {
  renderFilter();
  renderTree();
  renderDetail(ctx);
}

export async function refreshAll() {
  await Promise.all([loadExperiments(), loadTags()]);
  // 已展开节点强制重取，保证树上数据新鲜；已被删除的节点自动收起
  await Promise.all([...state.expanded].map(k => {
    const [type, id] = k.split(':');
    return fetchDetail(type, Number(id), true)
      .catch(() => state.expanded.delete(k));
  }));
  renderAll();
}

export const ctx = {
  state, LABEL, key, getObject, fetchDetail, refreshAll, renderAll,
  showToast, select,
};

document.getElementById('btn-new-experiment').onclick = () => {
  state.form = { type: 'experiment', parentId: null };
  state.editing = false;
  state.selected = null;
  renderAll();
};

refreshAll().catch(err => showToast(err.message));
