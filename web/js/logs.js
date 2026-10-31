async function renderLogs() {
  content().innerHTML = spinnerBlock('로그 설정을 불러오는 중...');
  try {
    const [s, channels] = await Promise.all([apiGetLogSettings(), apiListChannels()]);
    content().innerHTML = `
      <div class="card">
        <div class="card-header"><div><div class="card-title">로그 채널 & 문구 설정</div><div class="card-sub">상단 서버 DB 선택에 따라 해당 서버의 로그 설정만 따로 저장됩니다</div></div></div>
        <div class="card-pad">
          <div class="settings-grid">
            <div class="field"><label>구매 로그 채널</label><select class="select" id="lg-buyCh">${channelOpts(channels, s.buyChannel)}</select></div>
            <div class="field"><label>충전 로그 채널</label><select class="select" id="lg-chargeCh">${channelOpts(channels, s.chargeChannel)}</select></div>
          </div>
          <div class="settings-grid">
            <div class="field"><label>수동충전 로그 채널</label><select class="select" id="lg-manualChargeCh">${channelOpts(channels, s.manualChargeChannel)}</select></div>
            <div class="field"><label>로그인 로그 채널</label><select class="select" id="lg-loginCh">${channelOpts(channels, s.loginLogChannel)}</select></div>
          </div>
          <div class="settings-grid">
            <div class="field"><label>후기 로그 채널</label><select class="select" id="lg-reviewCh">${channelOpts(channels, s.reviewChannel)}</select></div>
            <div class="field"><label>입고 로그 채널</label><select class="select" id="lg-stockCh">${channelOpts(channels, s.stockChannel)}</select></div>
          </div>

          <div class="grid-2" style="align-items:start;margin:8px 0 20px">
            <div>
              <div class="field"><label>구매 로그 제목</label><input class="input" id="lg-buyTitle" value="${esc(s.buyTitle || '{카테고리}•{제품}')}" oninput="updateBuyPreviews()"/></div>
              <div class="field"><label>구매 로그 문구 템플릿</label><textarea class="textarea" id="lg-buyTpl" oninput="updateBuyPreviews()">${esc(s.buyTemplate)}</textarea><div class="hint">사용 변수: {유저}, {카테고리}, {제품}, {수량}, {총액}</div></div>
              <div class="field"><label>구매 로그 색상 (왼쪽 강조색)</label>${colorField('lg-buyColor', s.buyColor)}</div>
              <div class="field"><label>구매 로그 이미지 URL</label><input class="input" id="lg-buyImg" value="${esc(s.buyImageUrl)}" placeholder="https://..." oninput="updateBuyPreviews()"/></div>
            </div>
            <div>
              <div class="card-sub" style="margin-bottom:8px">구매 로그 미리보기</div>
              <div id="lg-buyPreview"></div>
            </div>
          </div>
          <div class="grid-2" style="align-items:start;margin:8px 0 20px">
            <div>
              <div class="field"><label>구매 DM 제목</label><input class="input" id="lg-dmTitle" value="${esc(s.dmTitle)}" oninput="updateBuyPreviews()"/></div>
              <div class="field"><label>구매 DM 문구</label><textarea class="textarea" id="lg-dmTpl" oninput="updateBuyPreviews()">${esc(s.dmTemplate)}</textarea><div class="hint">사용 변수: {유저}, {제품}, {수량}, {총액}, {서버}</div></div>
              <div class="field"><label>구매 DM 색상 (왼쪽 강조색)</label>${colorField('lg-dmColor', s.dmColor)}</div>
              <div class="field"><label>구매 DM 이미지 URL</label><input class="input" id="lg-dmImg" value="${esc(s.dmImageUrl)}" placeholder="https://..." oninput="updateBuyPreviews()"/></div>
            </div>
            <div>
              <div class="card-sub" style="margin-bottom:8px">구매 DM 미리보기</div>
              <div id="lg-dmPreview"></div>
            </div>
          </div>
          <div class="field"><label>충전 로그 문구 템플릿</label><textarea class="textarea" id="lg-chargeTpl">${esc(s.chargeTemplate)}</textarea><div class="hint">사용 변수: {user}, {amount}</div></div>
          <div class="field"><label>후기 로그 문구 템플릿</label><textarea class="textarea" id="lg-reviewTpl">${esc(s.reviewTemplate)}</textarea><div class="hint">사용 변수: {user}, {category}, {product}, {content}</div></div>
          <div class="grid-2" style="align-items:start;margin:8px 0 20px">
            <div>
              <div class="field"><label>입고 로그 제목</label><input class="input" id="lg-stockTitle" value="${esc(s.stockTitle || '입고')}" oninput="updateStockPreview()"/></div>
              <div class="field"><label>입고 로그 문구</label><textarea class="textarea" id="lg-stockTpl" oninput="updateStockPreview()">${esc(s.stockTemplate || '{제품} >> {수량}개 추가')}</textarea><div class="hint">사용 변수: {제품}, {카테고리}, {수량}, {이전재고}, {현재재고}, {서버}. 재고 수가 그대로면 보내지 않습니다.</div></div>
              ${switchRow('lg-stockEveryone', '입고 시 @everyone 핑', s.stockEveryone !== false)}
              <div class="hint" style="margin:-8px 0 12px">핑은 메시지에 붙습니다. 문구 안에 @everyone을 적어도 임베드에서는 핑이 나가지 않습니다.</div>
              <div class="settings-grid">
                <div class="field"><label>입고 로그 색상</label>${colorField('lg-stockColor', s.stockColor, 'updateStockPreview()')}</div>
                <div class="field"><label>입고 로그 이미지 URL</label><input class="input" id="lg-stockImg" value="${esc(s.stockImageUrl)}" placeholder="https://..." oninput="updateStockPreview()"/></div>
              </div>
            </div>
            <div>
              <div class="card-sub" style="margin-bottom:8px">입고 로그 미리보기</div>
              <div id="lg-stockPreview"></div>
            </div>
          </div>
          ${switchRow('lg-restockOn', '입고 시 구매자 전원 DM 보내기', !!s.restockDmEnabled)}
          <div class="field"><label>입고 DM 문구</label><textarea class="textarea" id="lg-restockTpl">${esc(s.restockDmTemplate)}</textarea><div class="hint">기본은 꺼져 있습니다. 사용 변수: {서버}, {제품}</div></div>

          <div class="form-actions"><button class="btn btn-primary" onclick="saveLogSettings()">저장</button></div>
        </div>
      </div>`;
    updateBuyPreviews();
    updateStockPreview();
    el('lg-stockEveryone')?.addEventListener('change', updateStockPreview);
  } catch (err) {
    content().innerHTML = errorBlock('로그 설정을 불러오지 못했습니다.', "renderLogs()");
  }
}
function updateBuyPreviews() {
  const buyTitle = (el('lg-buyTitle')?.value || '{카테고리}•{제품}').replaceAll('{카테고리}','카테고리').replaceAll('{제품}','상품').replaceAll('{유저}','@유저');
  const buyDesc = (el('lg-buyTpl')?.value || '').replaceAll('{유저}','@유저').replaceAll('{카테고리}','카테고리').replaceAll('{제품}','상품').replaceAll('{수량}','1').replaceAll('{총액}','3,000');
  const buyColor = el('lg-buyColor')?.value || '#5865F2';
  const buyImg = el('lg-buyImg')?.value || '';
  const dmTitle = el('lg-dmTitle')?.value || '구매 완료';
  const dmDesc = (el('lg-dmTpl')?.value || '').replaceAll('{유저}','@유저').replaceAll('{제품}','상품').replaceAll('{수량}','1').replaceAll('{총액}','3,000').replaceAll('{서버}','서버이름');
  const dmColor = el('lg-dmColor')?.value || '#57F287';
  const dmImg = el('lg-dmImg')?.value || '';
  if (el('lg-buyPreview')) {
    el('lg-buyPreview').innerHTML = `<div class="discord-preview" style="border-left-color:${esc(buyColor)}">
      <div class="dp-title">${esc(buyTitle)}</div>
      <div class="dp-desc">${esc(buyDesc)}</div>
      ${buyImg ? `<img class="dp-img" src="${esc(buyImg)}" alt="" onerror="this.style.display='none'"/>` : ''}
      <div class="dp-footer">구매 로그 · 방금</div>
    </div>`;
  }
  if (el('lg-dmPreview')) {
    el('lg-dmPreview').innerHTML = `<div class="discord-preview" style="border-left-color:${esc(dmColor)}">
      <div class="dp-title">${esc(dmTitle)}</div>
      <div class="dp-desc">상품: 한섭 스킨${dmDesc ? `<br>${esc(dmDesc)}` : ''}</div>
      <div class="dp-desc" style="margin-top:8px;background:#1e1f22;border-radius:6px;padding:8px 10px;font-family:monospace">지급코드 예시</div>
      ${dmImg ? `<img class="dp-img" src="${esc(dmImg)}" alt="" onerror="this.style.display='none'"/>` : ''}
      <div class="dp-footer">구매 DM · 왼쪽 색이 강조색입니다</div>
    </div>`;
  }
}
function updateStockPreview() {
  const title = (el('lg-stockTitle')?.value || '입고').replaceAll('{제품}','상품').replaceAll('{카테고리}','카테고리').replaceAll('{서버}','서버이름');
  const desc = (el('lg-stockTpl')?.value || '{제품} >> {수량}개 추가')
    .replaceAll('{제품}','상품').replaceAll('{카테고리}','카테고리').replaceAll('{수량}','3')
    .replaceAll('{이전재고}','1').replaceAll('{현재재고}','4').replaceAll('{서버}','서버이름');
  const color = el('lg-stockColor')?.value || '#57F287';
  const img = el('lg-stockImg')?.value || '';
  const ping = el('lg-stockEveryone')?.checked;
  if (!el('lg-stockPreview')) return;
  el('lg-stockPreview').innerHTML = `<div class="discord-preview" style="border-left-color:${esc(color)}">
    ${ping ? '<div class="dp-desc" style="color:#c9cdfb">@everyone</div>' : ''}
    <div class="dp-title">${esc(title)}</div>
    <div class="dp-desc">${esc(desc)}</div>
    ${img ? `<img class="dp-img" src="${esc(img)}" alt="" onerror="this.style.display='none'"/>` : ''}
    <div class="dp-footer">입고 로그 · 방금</div>
  </div>`;
}
async function saveLogSettings() {
  const data = {
    buyChannel: el('lg-buyCh').value, chargeChannel: el('lg-chargeCh').value, manualChargeChannel: el('lg-manualChargeCh').value, reviewChannel: el('lg-reviewCh').value, stockChannel: el('lg-stockCh').value,
    loginLogChannel: el('lg-loginCh').value,
    buyTitle: el('lg-buyTitle').value, buyTemplate: el('lg-buyTpl').value, chargeTemplate: el('lg-chargeTpl').value, reviewTemplate: el('lg-reviewTpl').value,
    stockTitle: el('lg-stockTitle').value, stockTemplate: el('lg-stockTpl').value, stockEveryone: el('lg-stockEveryone').checked,
    buyColor: el('lg-buyColor').value, buyImageUrl: el('lg-buyImg').value,
    stockColor: el('lg-stockColor').value, stockImageUrl: el('lg-stockImg').value,
    dmTitle: el('lg-dmTitle').value, dmTemplate: el('lg-dmTpl').value, dmColor: el('lg-dmColor').value, dmImageUrl: el('lg-dmImg').value,
    restockDmEnabled: el('lg-restockOn').checked, restockDmTemplate: el('lg-restockTpl').value
  };
  await apiSaveLogSettings(data);
  toast('로그 설정을 저장했습니다.');
}

async function renderLoginLogs() {
  content().innerHTML = spinnerBlock('로그인 로그를 불러오는 중...');
  try {
    const rows = await apiListLoginLogs();
    content().innerHTML = rows.length ? `<div class="card"><div class="card-header"><div class="card-title">웹패널 로그인</div></div>
      <div class="table-wrap"><table>
        <thead><tr><th>시각 (KST)</th><th>계정</th><th>IP</th><th>결과</th></tr></thead>
        <tbody>${rows.map((r) => `<tr>
          <td data-label="시각" class="time">${esc(fmtTime(r.createdAt))}</td>
          <td data-label="계정">${esc(r.username)}</td>
          <td data-label="IP" class="mono">${esc(r.ip)}</td>
          <td data-label="결과">${r.ok ? '<span class="badge badge-info">성공</span>' : '<span class="badge badge-muted">실패</span>'}</td>
        </tr>`).join('')}</tbody>
      </table></div></div>` : emptyBlock('로그인 기록이 없습니다', '웹패널에 로그인하면 여기에 IP가 남습니다.');
  } catch (err) {
    content().innerHTML = errorBlock('로그인 로그를 불러오지 못했습니다.', "renderLoginLogs()");
  }
}
