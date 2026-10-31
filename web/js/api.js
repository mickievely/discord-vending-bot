const API_BASE = '/api';

function apiUrl(path, { server = true } = {}) {
  const url = new URL(API_BASE + path, window.location.origin);
  if (server && currentServer) url.searchParams.set('serverId', currentServer);
  return url.toString();
}

async function apiRequest(path, { method = 'GET', body = null, auth = true, server = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== null) headers['Content-Type'] = 'application/json';
  if (auth) {
    const token = getAuth()?.token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(apiUrl(path, { server }), {
    method,
    headers,
    credentials: 'same-origin',
    body: body !== null ? JSON.stringify(body) : undefined
  });
  const ct = res.headers.get('content-type') || '';
  let data = null;
  if (ct.includes('json')) {
    data = await res.json().catch(() => null);
  } else {
    const text = await res.text();
    data = text || null;
  }
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login') {
      clearAuth();
      el('app')?.classList.add('hidden');
      el('login-screen')?.classList.remove('hidden');
    }
    if (data && typeof data === 'object') return data;
    throw new Error(typeof data === 'string' && data ? data : `HTTP ${res.status}`);
  }
  return data;
}

async function apiLogin(username, password, remember) {
  return apiRequest('/auth/login', { method: 'POST', body: { username, password, remember: !!remember }, auth: false, server: false });
}
async function apiLogout() { return apiRequest('/auth/logout', { method: 'POST', server: false }); }
async function apiMe() { return apiRequest('/auth/me', { server: false }); }
async function apiListServers() { return apiRequest('/servers', { server: false }); }
async function apiGetDashboard(days) {
  const n = Number(days);
  const q = [1, 7, 30, 90, 0].includes(n) ? `?days=${n}` : '';
  return apiRequest('/dashboard' + q);
}
async function apiListCategories() { return apiRequest('/categories'); }
async function apiCreateCategory(name) { return apiRequest('/categories', { method: 'POST', body: { name } }); }
async function apiUpdateCategory(id, name) { return apiRequest('/categories/' + encodeURIComponent(id), { method: 'PUT', body: { name } }); }
async function apiDeleteCategory(id) { return apiRequest('/categories/' + encodeURIComponent(id), { method: 'DELETE' }); }
async function apiReorderCategories(orderedIds) { return apiRequest('/categories/reorder', { method: 'PUT', body: { order: orderedIds } }); }
const _apiMem = {};
function cachedApi(key, ms, fn) {
  const hit = _apiMem[key];
  if (hit && Date.now() - hit.at < ms) return Promise.resolve(hit.data);
  return fn().then((data) => { _apiMem[key] = { at: Date.now(), data }; return data; });
}
function bustApi(prefix) {
  Object.keys(_apiMem).forEach((k) => { if (k.startsWith(prefix)) delete _apiMem[k]; });
}

async function apiListChannels() { return cachedApi('ch:' + currentServer, 60000, () => apiRequest('/channels')); }
async function apiListRoles() { return cachedApi('ro:' + currentServer, 60000, () => apiRequest('/roles')); }
async function apiListProducts() { return apiRequest('/products'); }
async function apiGetProduct(id) { return apiRequest('/products/' + encodeURIComponent(id)); }
async function apiCreateProduct(data) { return apiRequest('/products', { method: 'POST', body: data }); }
async function apiUpdateProduct(id, data) { return apiRequest('/products/' + encodeURIComponent(id), { method: 'PUT', body: data }); }
async function apiDeleteProduct(id) { return apiRequest('/products/' + encodeURIComponent(id), { method: 'DELETE' }); }
async function apiSaveStock(id, items, extra = {}) {
  return apiRequest('/products/' + encodeURIComponent(id) + '/stock', {
    method: 'PUT',
    body: { items, notifyBuyers: !!extra.notifyBuyers },
  });
}
async function apiReorderProducts(orderedIds) { return apiRequest('/products/reorder', { method: 'PUT', body: { order: orderedIds } }); }
async function apiGetPurchaseRole() { return apiRequest('/products/purchase-role'); }
async function apiSavePurchaseRole(roleId) { return apiRequest('/products/purchase-role', { method: 'PUT', body: { roleId } }); }
async function apiListStockInLogs() { return apiRequest('/stock-logs'); }
async function apiListOrders() { return apiRequest('/orders'); }
async function apiGetOrder(id) { return apiRequest('/orders/' + encodeURIComponent(id)); }
async function apiListUsers() { return cachedApi('us:' + currentServer, 12000, () => apiRequest('/users')); }
async function apiGetUser(id) { return apiRequest('/users/' + encodeURIComponent(id)); }
async function apiSetUserField(id, field, value) {
  bustApi('us:');
  return apiRequest('/users/' + encodeURIComponent(id), { method: 'PUT', body: { [field]: value } });
}
async function apiListVipTiers() { return apiRequest('/vip-tiers'); }
async function apiCreateVipTier(data) { return apiRequest('/vip-tiers', { method: 'POST', body: data }); }
async function apiUpdateVipTier(id, data) { return apiRequest('/vip-tiers/' + encodeURIComponent(id), { method: 'PUT', body: data }); }
async function apiDeleteVipTier(id) { return apiRequest('/vip-tiers/' + encodeURIComponent(id), { method: 'DELETE' }); }
async function apiListChargeRequests() { return apiRequest('/charges'); }
async function apiApproveCharge(id) { return apiRequest('/charges/' + encodeURIComponent(id) + '/approve', { method: 'POST' }); }
async function apiRejectCharge(id) { return apiRequest('/charges/' + encodeURIComponent(id) + '/reject', { method: 'POST' }); }
async function apiGetChargeSettings() { return apiRequest('/settings/charge'); }
async function apiSaveChargeSettings(data) { return apiRequest('/settings/charge', { method: 'PUT', body: data }); }
async function apiGetPanelSettings() { return apiRequest('/settings/panel'); }
async function apiSavePanelSettings(data) { return apiRequest('/settings/panel', { method: 'PUT', body: data }); }
async function apiGetLogSettings() { return apiRequest('/settings/logs'); }
async function apiSaveLogSettings(data) { return apiRequest('/settings/logs', { method: 'PUT', body: data }); }
async function apiListLoginLogs() { return apiRequest('/login-logs', { server: false }); }
async function apiSendAnnounce(data) { return apiRequest('/announce', { method: 'POST', body: data }); }
async function apiListDiscordCategories() { return apiRequest('/discord-categories'); }
