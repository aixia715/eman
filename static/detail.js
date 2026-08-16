export function renderDetail(ctx) {
  const root = document.getElementById('detail');
  const { state } = ctx;
  if (state.form) {
    root.innerHTML = '<p class="placeholder">表单在下一任务实现</p>';
    return;
  }
  if (!state.selected) {
    root.innerHTML = '<p class="placeholder">选择左侧节点查看详情</p>';
    return;
  }
  const obj = ctx.getObject(state.selected.type, state.selected.id);
  const pre = document.createElement('pre');
  pre.textContent = JSON.stringify(obj, null, 2);
  root.innerHTML = '';
  root.appendChild(pre);
}
