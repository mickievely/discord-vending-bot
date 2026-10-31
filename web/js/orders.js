let _orders = [], _orderSearch = '', _orderStatus = 'all', _orderOffset = 0;
const ORDER_PAGE_SIZE = 30;

async function renderOrders() {
  content().innerHTML = spinnerBlock('주문 내역을 불러오는 중...');
  try {
    _orders = await apiListOrders();
    content().innerHTML = `
      <div class="toolbar">
        <div class="search-box">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4-4"/></svg>
          <input class="input" type="text" placeholder="유저 ID 또는 상품명 검색..." value="${esc(_orderSearch)}" oninput="onOrderSearch(this.value)" />
        </div>
        <select class="select" style="width:auto" onchange="onOrderStatus(this.value)">
          <option value="all">전체 상태</option>
          <option value="completed" ${_orderStatus === 'completed' ? 'selected' : ''}>완료</option>
          <option value="pending" ${_orderStatus === 'pending' ? 'selected' : ''}>대기</option>
          <option value="refunded" ${_orderStatus === 'refunded' ? 'selected' : ''}>환불</option>
        </select>
      </div>
      <div id="order-table"></div>`;
    renderOrderTable();
  } catch (err) {
    content().innerHTML = errorBlock('주문 내역을 불러오지 못했습니다.', "renderOrders()");
  }
}
function onOrderSearch(v) { _orderSearch = v; _orderOffset = 0; renderOrderTable(); }
function onOrderStatus(v) { _orderStatus = v; _orderOffset = 0; renderOrderTable(); }
function pageOrders(dir) { _orderOffset = Math.max(0, _orderOffset + dir * ORDER_PAGE_SIZE); renderOrderTable(); }

function renderOrderTable() {
  const q = _orderSearch.trim().toLowerCase();
  const rows = _orders.filter((o) =>
    (_orderStatus === 'all' || o.status === _orderStatus) &&
    (!q || o.userId.toLowerCase().includes(q) || o.productName.toLowerCase().includes(q)));
  if (_orderOffset >= rows.length) _orderOffset = Math.max(0, Math.floor(Math.max(rows.length - 1, 0) / ORDER_PAGE_SIZE) * ORDER_PAGE_SIZE);
  const page = rows.slice(_orderOffset, _orderOffset + ORDER_PAGE_SIZE);
  const pageNo = rows.length ? Math.floor(_orderOffset / ORDER_PAGE_SIZE) + 1 : 0;
  const pageTotal = rows.length ? Math.ceil(rows.length / ORDER_PAGE_SIZE) : 0;
  el('order-table').innerHTML = page.length ? `<div class="table-wrap"><table>
    <thead><tr><th>주문 ID</th><th>디스코드 유저 ID</th><th>상품명</th><th>수량</th><th>총 금액</th><th>주문 시간</th><th>상태</th><th>재고</th></tr></thead>
    <tbody>${page.map((o) => `<tr>
      <td data-label="주문 ID" class="mono">${esc(o.id)}</td>
      <td data-label="유저 ID" class="mono" style="font-size:12px">${esc(o.userId)}</td>
      <td data-label="상품명">${esc(o.productName)}</td>
      <td data-label="수량">${o.qty}</td>
      <td data-label="총 금액" class="amount">${won(o.total)}</td>
      <td data-label="주문 시간" class="time">${esc(fmtTime(o.createdAt))}</td>
      <td data-label="상태">${statusBadge(o.status)}</td>
      <td data-label="재고"><div class="cell-actions">
        <button class="btn btn-sm" onclick="openOrderStockModal('${o.id}')">재고 보기</button>
        <button class="btn btn-sm btn-ghost" onclick="openOrderDrawer('${o.id}')">상세</button>
      </div></td>
    </tr>`).join('')}</tbody></table></div>
    <div class="form-actions" style="justify-content:space-between">
      <span class="text-muted" style="font-size:12px">${rows.length}건 중 ${_orderOffset + 1}-${Math.min(_orderOffset + ORDER_PAGE_SIZE, rows.length)} · ${pageNo}/${pageTotal}</span>
      <div class="cell-actions">
        <button class="btn btn-sm btn-ghost" onclick="pageOrders(-1)" ${_orderOffset <= 0 ? 'disabled' : ''}>이전</button>
        <button class="btn btn-sm btn-ghost" onclick="pageOrders(1)" ${_orderOffset + ORDER_PAGE_SIZE >= rows.length ? 'disabled' : ''}>다음</button>
      </div>
    </div>`
    : emptyBlock('주문이 없습니다', q ? '검색 결과가 없습니다' : '');
}

async function openOrderDrawer(id) {
  openDrawer({ title: '주문 상세', body: spinnerBlock('불러오는 중...') });
  const o = await apiGetOrder(id);
  el('drawer-body').innerHTML = `
    <div class="kv"><span class="k">주문 ID</span><span class="v mono">${esc(o.id)}</span></div>
    <div class="kv"><span class="k">상태</span><span class="v">${statusBadge(o.status)}</span></div>
    <div class="kv"><span class="k">디스코드 유저 ID</span><span class="v mono">${esc(o.userId)}</span></div>
    <div class="kv"><span class="k">상품명</span><span class="v">${esc(o.productName)}</span></div>
    <div class="kv"><span class="k">수량</span><span class="v">${o.qty}개</span></div>
    <div class="kv"><span class="k">총 금액</span><span class="v amount">${won(o.total)}</span></div>
    <div class="kv"><span class="k">주문 시간</span><span class="v time">${esc(fmtTime(o.createdAt))}</span></div>
    <div style="margin-top:20px">
      <label style="font-size:12px;color:var(--text-muted);font-weight:500">지급된 재고 내용</label>
      <div class="delivered-box mono">${o.delivered ? esc(o.delivered) : '지급 내역이 없습니다.'}</div>
    </div>`;
}

async function openOrderStockModal(id) {
  openModal({ title: '구매한 재고', sub: '불러오는 중...', body: spinnerBlock('불러오는 중...'), hideConfirm: true, confirmText: '닫기' });
  const o = await apiGetOrder(id);
  const items = (o.delivered || '').split('\n').map((s) => s.trim()).filter(Boolean);
  const list = items.length
    ? `<div class="stock-view-list">${items.map((code, i) => `
        <div class="stock-view-row">
          <span class="stock-view-idx">${i + 1}</span>
          <span class="stock-view-code mono">${esc(code)}</span>
          <button class="icon-btn" title="복사" onclick="copyText('${esc(code).replace(/'/g, "\\'")}', this)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
          </button>
        </div>`).join('')}</div>`
    : `<div class="delivered-box" style="text-align:center;color:var(--text-dim)">지급된 재고 내역이 없습니다.</div>`;
  setModalTitle('구매한 재고', esc(o.productName) + ' · ' + esc(o.id));
  el('modal-body').innerHTML = `
    <div class="kv"><span class="k">상품명</span><span class="v">${esc(o.productName)}</span></div>
    <div class="kv"><span class="k">수량</span><span class="v">${o.qty}개</span></div>
    <div class="kv"><span class="k">구매자</span><span class="v mono" style="font-size:12px">${esc(o.userId)}</span></div>
    <div style="margin-top:16px">
      <label style="font-size:12px;color:var(--text-muted);font-weight:500">지급된 재고 (${items.length}개)</label>
      ${list}
    </div>`;
}
