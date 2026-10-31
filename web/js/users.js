let _users = [], _userSearch = '', _userOffset = 0, _userVipTiers = [];
const USER_PAGE_SIZE = 40;

async function renderUsers() {
  content().innerHTML = spinnerBlock('유저 정보를 불러오는 중...');
  try {
    _users = await apiListUsers();
    content().innerHTML = `
      <div class="toolbar">
        <div class="search-box">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4-4"/></svg>
          <input class="input" type="text" placeholder="디스코드 유저 ID 검색..." value="${esc(_userSearch)}" oninput="onUserSearch(this.value)" />
        </div>
        <span class="card-sub" id="user-count"></span>
      </div>
      <div id="user-table"></div>`;
    renderUserTable();
  } catch (err) {
    content().innerHTML = errorBlock('유저 정보를 불러오지 못했습니다.', "renderUsers()");
  }
}
function onUserSearch(v) { _userSearch = v; _userOffset = 0; renderUserTable(); }
function pageUsers(dir) { _userOffset = Math.max(0, _userOffset + dir * USER_PAGE_SIZE); renderUserTable(); }
function openUser(id) { showView('user', { userId: String(id) }); }

function filteredUsers() {
  const q = _userSearch.trim().toLowerCase();
  return _users.filter((u) => !q || u.id.toLowerCase().includes(q));
}

function renderUserTable() {
  const rows = filteredUsers();
  if (el('user-count')) el('user-count').textContent = rows.length + '명';
  if (_userOffset >= rows.length) _userOffset = Math.max(0, Math.floor(Math.max(rows.length - 1, 0) / USER_PAGE_SIZE) * USER_PAGE_SIZE);
  const page = rows.slice(_userOffset, _userOffset + USER_PAGE_SIZE);
  const pageNo = rows.length ? Math.floor(_userOffset / USER_PAGE_SIZE) + 1 : 0;
  const pageTotal = rows.length ? Math.ceil(rows.length / USER_PAGE_SIZE) : 0;
  el('user-table').innerHTML = page.length ? `<div class="table-wrap"><table>
    <thead><tr><th>디스코드 유저 ID</th><th>VIP</th><th>잔액 (원)</th><th>총 구매액 (원)</th><th>주문 수</th><th></th></tr></thead>
    <tbody>${page.map((u) => `<tr>
      <td data-label="유저 ID" class="mono">${esc(u.id)}</td>
      <td data-label="VIP">${vipBadge(u.vip)}</td>
      <td data-label="잔액 (원)" class="amount">${won(u.balance)}</td>
      <td data-label="총 구매액 (원)" class="amount">${won(u.totalSpent)}</td>
      <td data-label="주문 수">${u.orderCount}건</td>
      <td data-label="관리"><button class="btn btn-sm" onclick="openUser('${u.id}')">수정</button></td>
    </tr>`).join('')}</tbody></table></div>
    <div class="form-actions" style="justify-content:space-between">
      <span class="text-muted" style="font-size:12px">${rows.length}명 중 ${_userOffset + 1}-${Math.min(_userOffset + USER_PAGE_SIZE, rows.length)} · ${pageNo}/${pageTotal}</span>
      <div class="cell-actions">
        <button class="btn btn-sm btn-ghost" onclick="pageUsers(-1)" ${_userOffset <= 0 ? 'disabled' : ''}>이전</button>
        <button class="btn btn-sm btn-ghost" onclick="pageUsers(1)" ${_userOffset + USER_PAGE_SIZE >= rows.length ? 'disabled' : ''}>다음</button>
      </div>
    </div>`
    : emptyBlock('유저가 없습니다', _userSearch ? '검색 결과가 없습니다' : '');
}

async function renderUserDetail() {
  const id = userIdFromPath();
  if (!id) { renderUsers(); return; }
  content().innerHTML = spinnerBlock('유저 정보를 불러오는 중...');
  try {
    const [u, tiers] = await Promise.all([apiGetUser(id), apiListVipTiers()]);
    _userVipTiers = tiers || [];
    paintUserDetail(u);
  } catch (err) {
    content().innerHTML = errorBlock('유저를 불러오지 못했습니다.', "renderUserDetail()");
  }
}

function paintUserDetail(u) {
  content().innerHTML = `
    <div class="toolbar">
      <button class="btn btn-sm btn-ghost" onclick="showView('users')">← 목록</button>
      <span class="mono" style="font-size:13px">${esc(u.id)}</span>
      <button class="btn btn-sm" onclick="copyText('${esc(u.id)}', this)">ID 복사</button>
    </div>
    <div class="stat-grid">
      ${statCard('잔액', won(u.balance), '지금 보유', '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>', '--success')}
      ${statCard('총 구매액', won(u.totalSpent), '완료 주문', '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/></svg>', '--info')}
      ${statCard('주문 수', (u.orderCount || 0) + '건', u.lastAt ? '최근 ' + fmtTime(u.lastAt) : '주문 없음', '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>', '--warning')}
      ${statCard('VIP', u.vip ? `<span class="vip-stat-name">${vipIconHtml(u.vip, 'vip-icon-sm')}${esc(u.vip.name)}</span>` : '없음', u.vip ? vipPerkMeta(u.vip) : '티어 미부여', '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3 7h7l-5.5 4.5L18 21l-6-3.8L6 21l1.5-7.5L2 9h7z"/></svg>', '--warning')}
    </div>
    <div class="grid-2" style="margin-top:16px;align-items:start">
      <div class="card">
        <div class="card-header"><div class="card-title">잔액 수정</div></div>
        <div class="card-pad">
          <div class="field"><label>잔액 지정</label>
            <div class="user-edit-row">
              <input class="input" type="number" min="0" id="ud-balance" value="${u.balance}" />
              <button class="btn btn-primary" onclick="saveUserBalance('${u.id}')">저장</button>
            </div>
          </div>
          <div class="field" style="margin-bottom:0"><label>더하거나 빼기</label>
            <div class="user-edit-row">
              <input class="input" type="number" id="ud-delta" placeholder="금액" />
              <button class="btn" onclick="nudgeUserBalance('${u.id}', 1)">추가</button>
              <button class="btn btn-danger" onclick="nudgeUserBalance('${u.id}', -1)">차감</button>
            </div>
          </div>
          <div class="field" style="margin:16px 0 0"><label>VIP 티어</label>
            <div class="user-edit-row">
              <select class="select" id="ud-vip">${_userVipOpts(u.vip)}</select>
              <button class="btn btn-primary" onclick="saveUserVip('${u.id}')">적용</button>
            </div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title">최근 충전</div><span class="card-sub">${(u.charges || []).length}건</span></div>
        <div class="table-wrap" style="border:none">${(u.charges || []).length ? `<table>
          <thead><tr><th>요청</th><th>금액</th><th>상태</th><th>시각</th></tr></thead>
          <tbody>${u.charges.map((c) => `<tr>
            <td class="mono" style="font-size:12px">${esc(c.id)}</td>
            <td class="amount text-success">+${won(c.amount)}</td>
            <td>${statusBadge(c.status)}</td>
            <td class="time">${esc(fmtTime(c.createdAt))}</td>
          </tr>`).join('')}</tbody></table>` : emptyBlock('충전 기록이 없습니다', '')}</div>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="card-header"><div class="card-title">최근 주문</div><span class="card-sub">${u.orderCount || 0}건</span></div>
      <div class="table-wrap" style="border:none">${(u.orders || []).length ? `<table>
        <thead><tr><th>주문 ID</th><th>상품</th><th>수량</th><th>금액</th><th>시각</th><th>상태</th></tr></thead>
        <tbody>${u.orders.map((o) => `<tr>
          <td class="mono">${esc(o.id)}</td>
          <td>${esc(o.productName)}</td>
          <td>${o.qty}</td>
          <td class="amount">${won(o.total)}</td>
          <td class="time">${esc(fmtTime(o.createdAt))}</td>
          <td>${statusBadge(o.status)}</td>
        </tr>`).join('')}</tbody></table>` : emptyBlock('주문이 없습니다', '')}</div>
    </div>`;
  enhanceSelects(content());
}

async function saveUserBalance(id) {
  const value = parseInt(el('ud-balance')?.value, 10);
  if (isNaN(value) || value < 0) { toast('0 이상의 숫자를 입력하세요.', 'error'); return; }
  try {
    paintUserDetail(await apiSetUserField(id, 'balance', value));
    toast('잔액을 ' + won(value) + '(으)로 저장했습니다.');
  } catch { toast('잔액 저장에 실패했습니다.', 'error'); }
}

function vipPerkMeta(vip) {
  const bits = [];
  const buy = parseInt(vip.purchaseDiscountPct ?? vip.discountPct, 10) || 0;
  const charge = parseInt(vip.chargeBonusPct, 10) || 0;
  if (buy) bits.push('구매 -' + buy + '%');
  if (charge) bits.push('충전 +' + charge + '%');
  return bits.join(' · ') || '혜택 없음';
}

function _userVipOpts(vip) {
  const sel = vip && vip.id ? String(vip.id) : '';
  return `<option value="">자동 / 없음</option>` + _userVipTiers.map((t) =>
    `<option value="${esc(t.id)}" ${String(t.id) === sel ? 'selected' : ''}>${esc(t.name)}</option>`
  ).join('');
}

async function saveUserVip(id) {
  const tid = el('ud-vip')?.value || '';
  try {
    paintUserDetail(await apiSetUserField(id, 'vipTierId', tid));
    toast(tid ? 'VIP 티어를 적용했습니다.' : 'VIP 티어를 해제했습니다.');
  } catch { toast('VIP 저장에 실패했습니다.', 'error'); }
}

async function nudgeUserBalance(id, sign) {
  const n = parseInt(el('ud-delta')?.value, 10);
  if (!n || n <= 0) { toast('금액을 입력하세요.', 'error'); return; }
  try {
    const u = await apiSetUserField(id, 'delta', n * sign);
    paintUserDetail(u);
    toast(sign > 0 ? won(n) + '을 추가했습니다.' : won(n) + '을 차감했습니다.');
  } catch { toast('잔액 변경에 실패했습니다.', 'error'); }
}
