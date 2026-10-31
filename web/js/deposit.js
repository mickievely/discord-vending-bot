let _charges = [], _chargeSearch = '', _chargeOffset = 0;
const CHARGE_PAGE_SIZE = 5;

async function renderCharges() {
  content().innerHTML = spinnerBlock('충전 요청을 불러오는 중...');
  try {
    const [charges, settings, channels, roles] = await Promise.all([apiListChargeRequests(), apiGetChargeSettings(), apiListChannels(), apiListRoles()]);
    _charges = charges;
    const pending = _charges.filter((c) => c.status === 'pending');
    content().innerHTML = `
      <div class="card" style="margin-bottom:20px">
        <div class="card-header"><div class="card-title">충전 대기 요청</div><span class="card-sub">${pending.length}건 대기 중</span></div>
        <div class="toolbar" style="padding:0 16px 12px">
          <div class="search-box">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4-4"/></svg>
            <input class="input" type="text" placeholder="요청 ID, 유저 ID, 입금자명 검색..." value="${esc(_chargeSearch)}" oninput="onChargeSearch(this.value)" />
          </div>
        </div>
        <div id="charge-table"></div>
      </div>

      <div class="card">
        <div class="card-header"><div class="card-title">충전 설정</div></div>
        <div class="card-pad">
          <form id="charge-settings-form" onsubmit="return saveChargeSettings(event)">
            <div class="settings-grid">
              <div>
                <div style="font-size:12px;font-weight:600;color:var(--accent);margin-bottom:12px">계좌 1</div>
                <div class="field"><label>은행명</label><input class="input" id="cs-aosBank" value="${esc(settings.aosBank)}"/></div>
                <div class="field"><label>계좌번호</label><input class="input" id="cs-aosAccount" value="${esc(settings.aosAccount)}"/></div>
                <div class="field"><label>예금주</label><input class="input" id="cs-aosHolder" value="${esc(settings.aosHolder)}"/></div>
                <div class="field"><label>Pushbullet 토큰</label><input class="input" id="cs-aosPushbullet" value="${esc(settings.aosPushbullet)}"/></div>
              </div>
              <div>
                <div style="font-size:12px;font-weight:600;color:var(--accent);margin-bottom:12px">계좌 2</div>
                <div class="field"><label>은행명</label><input class="input" id="cs-iosBank" value="${esc(settings.iosBank)}"/></div>
                <div class="field"><label>계좌번호</label><input class="input" id="cs-iosAccount" value="${esc(settings.iosAccount)}"/></div>
                <div class="field"><label>예금주</label><input class="input" id="cs-iosHolder" value="${esc(settings.iosHolder)}"/></div>
                <div class="field"><label>충전로그 채널</label><select class="select" id="cs-iosLogChannel">${channelOpts(channels, settings.iosLogChannel)}</select></div>
              </div>
            </div>
            <div class="settings-grid">
              <div class="field"><label>최소충전 금액</label><input class="input" type="number" min="1" step="1" id="cs-minChargeAmount" value="${esc(settings.minChargeAmount || 1)}"/></div>
              <div class="field"><label>수동충전 역할</label><select class="select" id="cs-approveRole">${roleOpts(roles, settings.approveRole || settings.manualChargeRole)}</select></div>
            </div>
            ${switchRow('cs-manualNotice', '수동충전 메시지 전송', settings.manualChargeNotice !== false)}
            <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
              <div style="font-size:12px;font-weight:600;color:var(--accent);margin-bottom:12px">코인 (NOWPayments)</div>
              <div class="hint" style="margin-bottom:10px">API 키·IPN Secret·공개 URL은 서버 <code>.env</code> (NOWPAYMENTS_*, WEB_PUBLIC_URL)</div>
              ${switchRow('cs-cryptoEnabled', '코인 자동충전 사용', !!settings.cryptoEnabled)}
              <div class="field"><label>결제 코인 (pay_currency)</label><input class="input" id="cs-cryptoCurrency" placeholder="usdttrc20" value="${esc(settings.cryptoPayCurrency || 'usdttrc20')}"/></div>
            </div>
            <div class="form-actions"><button type="submit" class="btn btn-primary">설정 저장</button></div>
          </form>
        </div>
      </div>`;
    renderChargeTable();
  } catch (err) {
    content().innerHTML = errorBlock('충전 정보를 불러오지 못했습니다.', "renderCharges()");
  }
}

function renderChargeTable() {
  const q = _chargeSearch.trim().toLowerCase();
  const rows = _charges.filter((c) => {
    if (!q) return true;
    return [c.id, c.platform, c.userId, c.depositor, c.amount, c.status]
      .some((v) => String(v || '').toLowerCase().includes(q));
  });
  if (_chargeOffset >= rows.length) _chargeOffset = Math.max(0, Math.floor(Math.max(rows.length - 1, 0) / CHARGE_PAGE_SIZE) * CHARGE_PAGE_SIZE);
  const pageRows = rows.slice(_chargeOffset, _chargeOffset + CHARGE_PAGE_SIZE);
  const pageNo = rows.length ? Math.floor(_chargeOffset / CHARGE_PAGE_SIZE) + 1 : 0;
  const pageTotal = rows.length ? Math.ceil(rows.length / CHARGE_PAGE_SIZE) : 0;
  el('charge-table').innerHTML = pageRows.length ? `<div class="table-wrap" style="border:none;border-radius:0"><table>
    <thead><tr><th>요청 ID</th><th>계좌</th><th>유저 ID</th><th>입금자명</th><th>금액</th><th>요청 시간</th><th>상태</th><th>처리 스태프</th><th>승인/거절</th></tr></thead>
    <tbody>${pageRows.map((c) => `<tr>
      <td data-label="요청 ID" class="mono" style="font-size:12px">${esc(c.id)}</td>
      <td data-label="계좌"><span class="badge ${c.platform === 'AOS' ? 'badge-info' : (c.platform === 'CRYPTO' ? 'badge-success' : 'badge-muted')}">${chargeAccountLabel(c.platform)}</span></td>
      <td data-label="유저 ID" class="mono" style="font-size:12px">${esc(c.userId)}</td>
      <td data-label="입금자명">${esc(c.depositor)}</td>
      <td data-label="금액" class="amount text-success">+${won(c.amount)}</td>
      <td data-label="요청 시간" class="time">${esc(fmtTime(c.createdAt))}</td>
      <td data-label="상태">${statusBadge(c.status)}</td>
      <td data-label="처리 스태프" style="font-size:12px;color:var(--text-muted)">${esc(c.approvedBy || '-')}${c.approvedAt ? `<div class="time">${esc(fmtTime(c.approvedAt))}</div>` : ''}</td>
      <td data-label="승인/거절">${c.status === 'pending' ? `<div class="cell-actions">
        <button class="btn btn-sm btn-success" onclick="approveCharge('${c.id}')">승인</button>
        <button class="btn btn-sm btn-danger" onclick="rejectCharge('${c.id}')">거절</button>
      </div>` : '<span class="text-muted" style="font-size:12px">처리 완료</span>'}</td>
    </tr>`).join('')}</tbody></table></div>
    <div class="form-actions" style="justify-content:space-between;padding:12px 16px 16px">
      <span class="text-muted" style="font-size:12px">${rows.length}건 중 ${_chargeOffset + 1}-${Math.min(_chargeOffset + CHARGE_PAGE_SIZE, rows.length)} · ${pageNo}/${pageTotal}</span>
      <div class="cell-actions">
        <button class="btn btn-sm btn-ghost" onclick="pageCharges(-1)" ${_chargeOffset <= 0 ? 'disabled' : ''}>이전</button>
        <button class="btn btn-sm btn-ghost" onclick="pageCharges(1)" ${_chargeOffset + CHARGE_PAGE_SIZE >= rows.length ? 'disabled' : ''}>다음</button>
      </div>
    </div>`
    : emptyBlock('충전 요청이 없습니다', q ? '검색 결과가 없습니다' : '');
}

function chargeAccountLabel(platform) {
  const p = String(platform || '').toUpperCase();
  if (p === 'IOS') return '계좌 2';
  if (p === 'CRYPTO') return '코인';
  return '계좌 1';
}

function onChargeSearch(v) {
  _chargeSearch = v;
  _chargeOffset = 0;
  renderChargeTable();
}

function pageCharges(dir) {
  _chargeOffset = Math.max(0, _chargeOffset + dir * CHARGE_PAGE_SIZE);
  renderChargeTable();
}

async function approveCharge(id) {
  await apiApproveCharge(id);
  toast('충전 요청을 승인했습니다.');
  _charges = await apiListChargeRequests();
  _chargeOffset = Math.min(_chargeOffset, Math.max(0, _charges.length - CHARGE_PAGE_SIZE));
  renderChargeTable(); refreshChargeBadge();
}
async function rejectCharge(id) {
  await apiRejectCharge(id);
  toast('충전 요청을 거절했습니다.', 'info');
  _charges = await apiListChargeRequests();
  _chargeOffset = Math.min(_chargeOffset, Math.max(0, _charges.length - CHARGE_PAGE_SIZE));
  renderChargeTable(); refreshChargeBadge();
}

async function saveChargeSettings(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  btn.disabled = true; btn.textContent = '저장 중...';
  const data = {
    aosBank: el('cs-aosBank').value, aosAccount: el('cs-aosAccount').value, aosHolder: el('cs-aosHolder').value, aosPushbullet: el('cs-aosPushbullet').value,
    iosBank: el('cs-iosBank').value, iosAccount: el('cs-iosAccount').value, iosHolder: el('cs-iosHolder').value, iosLogChannel: el('cs-iosLogChannel').value,
    approveRole: el('cs-approveRole').value,
    minChargeAmount: parseInt(el('cs-minChargeAmount').value, 10) || 1,
    manualChargeNotice: el('cs-manualNotice').checked,
    cryptoEnabled: el('cs-cryptoEnabled').checked,
    cryptoPayCurrency: el('cs-cryptoCurrency').value
  };
  await apiSaveChargeSettings(data);
  btn.disabled = false; btn.textContent = '설정 저장';
  toast('충전 설정을 저장했습니다.');
  return false;
}
