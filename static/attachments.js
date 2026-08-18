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
