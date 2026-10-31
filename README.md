# 디스코드 자판기 봇

디스코드 서버 **자판기 · 잔액 · VIP · 자동 충전**과 **웹 관리 패널**을 한 번에 쓸 수 있는 오픈소스 봇입니다.

MIT · 자유롭게 사용·수정·배포 가능

---

## 기능

- **Components v2** 자판기 패널
- **자동 충전** — Android · iPhone ([`자충.txt`](./자충.txt)) · **코인 (NOWPayments)**
- **VIP** 구매·충전 할인
- **자동 구매** — 잔액 차감 후 재고 DM 지급
- **입고 알림** — 재고 등록 시 채널·구매자 알림
- **구매 로그** · **구매 후기** — 채널 로그 + 구매자 후기 작성

**웹 패널** — 상품·재고, 충전 승인, VIP·로그·공지 설정

---

## 빠르게 쓰기

Python **3.11+** 깔려 있으면 됨.

```bash
git clone https://github.com/mickievely/discord-vending-bot.git
cd discord-vending-bot
pip install -r requirements.txt
```

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

NOWPAYMENTS_API_KEY=
NOWPAYMENTS_IPN_SECRET=
WEB_PUBLIC_URL=https://결제콜백받을_공개주소
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
