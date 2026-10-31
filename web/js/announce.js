async function renderAnnounce() {
  content().innerHTML = spinnerBlock('공지 대상을 불러오는 중...');
  try {
    const [channels, roles, users] = await Promise.all([apiListChannels(), apiListRoles(), apiListUsers()]);
    content().innerHTML = `
      <div class="card">
        <div class="card-header"><div><div class="card-title">공지 / 개인 DM</div><div class="card-sub">채널에 올리고, 특정 사람이나 역할에게도 DM을 보냅니다</div></div></div>
        <div class="card-pad">
          <div class="grid-2" style="align-items:start">
            <div>
              <div class="field"><label>제목</label><input class="input" id="an-title" value="공지" oninput="updateAnnouncePreview()"/></div>
              <div class="field"><label>내용</label><textarea class="textarea" id="an-desc" rows="7" placeholder="공지 내용을 입력하세요" oninput="updateAnnouncePreview()"></textarea></div>
              <div class="field"><label>색상</label>${colorField('an-color', '#5865F2', 'updateAnnouncePreview()')}</div>
              <div class="field"><label>이미지 URL</label><input class="input" id="an-img" placeholder="https://..." oninput="updateAnnouncePreview()"/></div>
              ${switchRow('an-postCh', '채널에도 올리기', true)}
              <div class="field"><label>올릴 채널</label><select class="select" id="an-ch">${channelOpts(channels, '')}</select></div>
            </div>
            <div>
              <div class="card-sub" style="margin-bottom:8px">미리보기</div>
              <div id="an-preview"></div>
              <div class="field" style="margin-top:16px"><label>역할 DM</label>
                <div class="pick-list" id="an-roles">${roles.length ? roles.map((r) => pickSwitch({ value: r.id, cls: 'an-role', label: r.name })).join('') : '<div class="state-desc" style="padding:10px">역할을 불러오지 못했습니다.</div>'}</div>
              </div>
              <div class="field"><label>유저 DM</label>
                <input class="input" id="an-userQ" placeholder="유저 ID 검색" oninput="filterAnnounceUsers()" style="margin-bottom:8px"/>
                <div class="pick-list" id="an-users">${users.length ? users.map((u) => pickSwitch({ value: u.id, cls: 'an-user', label: u.id, meta: `${Number(u.orderCount || 0)}건`, extra: `data-uid="${esc(u.id)}"` })).join('') : '<div class="state-desc" style="padding:10px">등록된 유저가 없습니다. 아래에 ID를 직접 넣으세요.</div>'}</div>
              </div>
              <div class="field"><label>추가 유저 ID</label><textarea class="textarea" id="an-extra" rows="3" placeholder="1234567890, @유저 또는 한 줄에 하나"></textarea><div class="hint">멘션이나 숫자 ID를 붙여넣어도 됩니다</div></div>
              ${switchRow('an-buyers', '구매자 전원에게도 DM', false)}
            </div>
          </div>
          <div class="form-actions"><button class="btn btn-primary" id="an-send" onclick="sendAnnounce()">공지 보내기</button></div>
        </div>
      </div>`;
    updateAnnouncePreview();
  } catch (err) {
    content().innerHTML = errorBlock('공지 화면을 불러오지 못했습니다.', "renderAnnounce()");
  }
}
function updateAnnouncePreview() {
  const title = el('an-title')?.value || '공지';
  const desc = el('an-desc')?.value || '';
  const color = el('an-color')?.value || '#5865F2';
  const img = el('an-img')?.value || '';
  if (!el('an-preview')) return;
  el('an-preview').innerHTML = `<div class="discord-preview" style="border-left-color:${esc(color)}">
    <div class="dp-title">${esc(title)}</div>
    <div class="dp-desc">${esc(desc || '내용을 입력하면 여기에 미리보기가 됩니다.')}</div>
    ${img ? `<img class="dp-img" src="${esc(img)}" alt="" onerror="this.style.display='none'"/>` : ''}
    <div class="dp-footer">공지 · DM에도 같은 임베드가 갑니다</div>
  </div>`;
}
function filterAnnounceUsers() {
  const q = (el('an-userQ')?.value || '').trim();
  document.querySelectorAll('#an-users .pick-item').forEach((row) => {
    row.style.display = !q || (row.dataset.uid || '').includes(q) ? '' : 'none';
  });
}
async function sendAnnounce() {
  const btn = el('an-send');
  const roleIds = [...document.querySelectorAll('.an-role:checked')].map((n) => n.value);
  const userIds = [...document.querySelectorAll('.an-user:checked')].map((n) => n.value);
  const extra = el('an-extra').value;
  const postChannel = el('an-postCh').checked;
  const channelId = el('an-ch').value;
  if (postChannel && !channelId && !roleIds.length && !userIds.length && !extra.trim() && !el('an-buyers').checked) {
    return toast('채널, 역할, 유저 중 하나 이상 선택하세요.', 'error');
  }
  btn.disabled = true;
  btn.textContent = '보내는 중...';
  try {
    const res = await apiSendAnnounce({
      title: el('an-title').value,
      description: el('an-desc').value,
      color: el('an-color').value,
      imageUrl: el('an-img').value,
      postChannel,
      channelId,
      roleIds,
      userIds,
      extraUserIds: extra,
      buyers: el('an-buyers').checked
    });
    if (res && res.ok === false) return toast(res.error || '공지 전송 실패', 'error');
    const bits = [];
    if (res.channelOk) bits.push('채널 게시');
    bits.push(`DM ${res.dmOk || 0}/${res.dmTotal || 0}`);
    if (res.dmFail) bits.push(`실패 ${res.dmFail}`);
    toast((bits.join(' · ') || '공지를 보냈습니다.') + (res.roleWarning ? ` · ${res.roleWarning}` : ''));
  } catch (err) {
    toast('공지를 보내지 못했습니다.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '공지 보내기';
  }
}
