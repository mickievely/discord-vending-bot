# 디스코드 자판기 봇

디스코드 서버 **자판기 · 잔액 · VIP · 자동 충전**과 **웹 관리 패널**을 한 번에 쓸 수 있는 오픈소스 봇입니다.

MIT · 자유롭게 사용·수정·배포 가능

---

## 기능

| 디스코드 | 웹 패널 | 자동 충전 |
|----------|---------|-----------|
| Components v2 자판기 패널 | 상품·카테고리·재고 | Android Pushbullet |
| 구매 · 충전 · 내 정보 | 주문 · 유저 · 충전 승인 | iOS 단축어 / 웹훅 |
| VIP 할인 · 관리자 UI | VIP · 로그 · 공지 DM | [`자충.txt`](./자충.txt) 참고 |

데이터는 서버(guild)마다 `data/servers/<guild_id>/server.db` (SQLite)에 저장됩니다.

---

## 설치

**필요:** Python 3.11+

```bash
git clone https://github.com/mickievely/discord-vending-bot.git
cd discord-vending-bot

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## 디스코드 봇 설정

1. [Developer Portal](https://discord.com/developers/applications)에서 앱 생성  
2. **Bot** → 토큰 발급 → 아래 `.env`의 `DISCORD_TOKEN`에만 입력  
3. **Privileged Gateway Intents**  
   - Message Content Intent (충전 문자 파싱)  
   - Server Members Intent (역할·VIP, 필요 시)  
4. **OAuth2 → URL Generator** → `bot` + `applications.commands` → 서버 초대  

---

## 환경 변수 (`.env`)

프로젝트 루트에 `.env` 파일을 만들고 설정합니다. **Git에 올리지 마세요.**

```env
DISCORD_TOKEN=봇_토큰
DATA_DIR=./data

ROOT_USER_IDS=디스코드_유저_ID

WEB_ADMIN_ID=admin
WEB_ADMIN_PASSWORD=강한_비밀번호

WEB_PANEL_HOST=127.0.0.1
WEB_PANEL_PORT=8765
WEB_PANEL_AUTO_START=1
```

| 변수 | 설명 |
|------|------|
| `DISCORD_TOKEN` | 필수 · 봇 토큰 |
| `WEB_ADMIN_PASSWORD` | 필수 · 웹 패널 로그인 비밀번호 |
| `ROOT_USER_IDS` | 선택 · 슈퍼관리 ID (콤마 구분, `/관리자패널`) |
| `WEB_PANEL_HOST` | `127.0.0.1` = 본인 PC만 / `0.0.0.0` = 외부 접속 |
| `WEB_PANEL_AUTO_START` | `1`이면 `bot.py` 실행 시 웹 패널 같이 켬 |

선택: `WEB_JWT_SECRET`, `WEB_SESSION_TTL`, `PRODUCT_ADD_WEBHOOK_URL`

---

## 실행

```bash
python bot.py
```

| 확인 | |
|------|--|
| 봇 | 콘솔 `ready: ...` |
| 웹 패널 | `http://127.0.0.1:8765` (또는 `.env` 포트) |
| 로그인 | `WEB_ADMIN_ID` / `WEB_ADMIN_PASSWORD` |

---

## 디스코드 사용법

### 슬래시 명령

| 명령 | 설명 |
|------|------|
| `/자판기` | 자판기 패널 채널에 게시 |
| `/자판기패널` | 관리자용 패널 게시 |
| `/내정보` | 내 잔액·구매 정보 |
| `/정보` | 유저 정보 조회 (관리자) |
| `/수동충전` | 잔액 추가·차감 |
| `/vip부여` | VIP 티어 부여 |
| `/관리자패널` | ROOT 전용 (서버 DB 삭제 등) |

### 유저

**충전** → 계좌 입금 · 자동충전 연동 → **구매** → 재고 지급 → **정보**에서 내역 확인

---

## 웹 패널

1. **상품 관리** — 카테고리, 상품, 재고 (한 줄 = 1개)  
2. **충전 관리** — 승인/거절, AOS·iOS 계좌  
3. **자판기 패널 설정** — 제목, 색, 이미지  
4. **VIP · 로그 · 공지**  

여러 서버 운영 시 상단에서 **서버 선택**으로 DB 전환.

---

## 트러블슈팅

| 증상 | 체크 |
|------|------|
| 봇 안 켜짐 | `.env` 토큰, Intent, 서버 초대 |
| 버튼/슬래시 무반응 | 권한, `commands synced` 로그 |
| 웹 패널 접속 불가 | `WEB_PANEL_AUTO_START`, 방화벽, 포트 |
| 자동 충전 실패 | Pushbullet / iOS 설정, [`자충.txt`](./자충.txt), 입금자명 |

---

## 폴더

```
bot.py          진입점 (봇 + 라우팅)
web_panel.py    웹 API
config.py       .env 로드
cogs/           슬래시 명령
services/       구매·충전·알림
db/             SQLite
ui/             Discord UI
web/            패널 UI
```

---

## 라이선스

[MIT](./LICENSE)
