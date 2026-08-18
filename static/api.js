async function handle(res) {
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`;
    try {
      const data = await res.json();
      if (data.error) msg = data.error;
    } catch { /* 忽略非 JSON 响应体 */ }
    throw new Error(msg);
  }
  return res.json();
}

const API = {
  async req(method, path, body) {
    let res;
    try {
      res = await fetch('/api' + path, {
        method,
        headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new Error('网络错误：无法连接服务器');
    }
    return handle(res);
  },
  async upload(path, file) {
    const form = new FormData();
    form.append('file', file);
    let res;
    try {
      // 不要手工设 Content-Type：必须让浏览器生成带 boundary 的 multipart 头
      res = await fetch('/api' + path, { method: 'POST', body: form });
    } catch {
      throw new Error('网络错误：无法连接服务器');
    }
    return handle(res);
  },
  get: (p) => API.req('GET', p),
  post: (p, b) => API.req('POST', p, b),
  patch: (p, b) => API.req('PATCH', p, b),
  del: (p) => API.req('DELETE', p),
};

export default API;
