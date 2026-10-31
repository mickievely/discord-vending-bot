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

데이터는 `data/servers/<guild_id>/server.db` (SQLite)에 저장됩니다. **서버는 `.env`의 `DISCORD_GUILD_ID` 하나만** 사용합니다.

---

## 빠르게 쓰기

Python **3.11+** 깔려 있으면 됨.

```bash
git clone https://github.com/mickievely/discord-vending-bot.git
cd discord-vending-bot
pip install -r requirements.txt
```

`.env` 세팅하고 (아래 참고)

```bash
python bot.py
```

---

## 환경 변수 (`.env`)

```env
DISCORD_TOKEN=봇_토큰
DISCORD_GUILD_ID=서버_ID

DATA_DIR=./data

WEB_ADMIN_ID=admin
WEB_ADMIN_PASSWORD=강한_비밀번호

WEB_PANEL_HOST=127.0.0.1
WEB_PANEL_PORT=8765
WEB_PANEL_AUTO_START=1
```

---

## 명령어 안내

| 명령 | 설명 |
|------|------|
| `/자판기` | 자판기 패널 채널에 게시 |
| `/자판기패널` | 관리자용 패널 게시 |
| `/내정보` | 내 잔액·구매 정보 |
| `/정보` | 유저 정보 조회 (관리자) |
| `/수동충전` | 잔액 추가·차감 |
| `/vip부여` | VIP 티어 부여 |

---

## 웹 패널

1. **상품 관리** — 카테고리, 상품, 재고 (한 줄 = 1개)  
2. **충전 관리** — 승인/거절, AOS·iOS 계좌  
3. **자판기 패널 설정** — 제목, 색, 이미지  
4. **VIP · 로그 · 공지**  

---

## 라이선스

[MIT](./LICENSE)
