async function renderPanel() {
  content().innerHTML = spinnerBlock('패널 설정을 불러오는 중...');
  try {
    const s = await apiGetPanelSettings();
    content().innerHTML = `
      <div class="grid-2" style="align-items:start">
        <div class="card">
          <div class="card-header"><div class="card-title">패널 설정</div></div>
          <div class="card-pad">
            <div class="field"><label>자판기 제목</label><input class="input" id="pn-title" value="${esc(s.title)}" oninput="updatePanelPreview()"/></div>
            <div class="field"><label>자판기 설명</label><textarea class="textarea" id="pn-desc" oninput="updatePanelPreview()">${esc(s.description)}</textarea></div>
            <div class="field"><label>이미지 URL</label><input class="input" id="pn-img" value="${esc(s.imageUrl)}" placeholder="https://..." oninput="updatePanelPreview()"/></div>
            <div class="field"><label>임베드 색상</label>${colorField('pn-color', s.color, 'updatePanelPreview()')}</div>
            <div class="form-actions"><button class="btn btn-primary" onclick="savePanelSettings()">저장</button></div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">라이브 미리보기</div><span class="card-sub">자판기 버튼</span></div>
          <div class="card-pad"><div id="panel-preview"></div></div>
        </div>
      </div>`;
    updatePanelPreview();
  } catch (err) {
    content().innerHTML = errorBlock('패널 설정을 불러오지 못했습니다.', "renderPanel()");
  }
}
function updatePanelPreview() {
  const title = el('pn-title').value.trim(), desc = el('pn-desc').value.trim(), img = el('pn-img').value.trim(), color = el('pn-color').value;
  el('panel-preview').innerHTML = `
    <div class="discord-preview" style="border-left-color:${esc(color)}">
      ${title ? `<div class="dp-title">${esc(title)}</div>` : ''}
      ${desc ? `<div class="dp-desc">${esc(desc)}</div>` : ''}
      ${img ? `<img class="dp-img" src="${esc(img)}" alt="패널 이미지" onerror="this.style.display='none'"/>` : ''}
      <div class="dp-actions">
        <span class="dp-btn">구매</span>
        <span class="dp-btn">제품</span>
        <span class="dp-btn">충전</span>
        <span class="dp-btn">정보</span>
      </div>
    </div>`;
}
async function savePanelSettings() {
  const data = { title: el('pn-title').value, description: el('pn-desc').value, imageUrl: el('pn-img').value, color: el('pn-color').value };
  await apiSavePanelSettings(data);
  toast('패널 설정을 저장했습니다.');
}
