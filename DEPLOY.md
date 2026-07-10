# 배포 가이드 — URL로 바로 온라인 대전

목표: 친구에게 링크만 보내면 브라우저에서 바로 대전.
구성: **클라이언트 = GitHub Pages** (정적) + **서버 = Render** (WebSocket, 무료).

## 0. 준비물
- GitHub 계정 (https://github.com)
- Render 계정 (https://render.com — GitHub 계정으로 가입 가능)

## 1. GitHub에 올리기
로컬 커밋은 이미 되어 있다. GitHub에서 새 저장소를 만들고 push:

```bash
# GitHub에서 새 저장소(예: 2dWebFightGame)를 만든 뒤:
git remote add origin https://github.com/<내아이디>/2dWebFightGame.git
git push -u origin main
```

## 2. 서버 배포 (Render)
1. https://dashboard.render.com → **New → Blueprint**
2. 방금 만든 GitHub 저장소 연결 → `render.yaml`이 자동 인식됨 → **Apply**
3. 배포가 끝나면 서버 주소가 생긴다: `https://fight-server-XXXX.onrender.com`
   → WebSocket 주소는 **`wss://fight-server-XXXX.onrender.com`** (https → wss)

## 3. 클라이언트에 서버 주소 연결
[docs/config.js](docs/config.js) 의 주소를 바꾸고 push:

```js
window.GAME_SERVER = "wss://fight-server-XXXX.onrender.com";
```

```bash
git add docs/config.js && git commit -m "Set production server URL" && git push
```

## 4. GitHub Pages 켜기
1. GitHub 저장소 → **Settings → Pages**
2. Source: **Deploy from a branch**, Branch: **main**, Folder: **/docs** → Save
3. 1~2분 후 `https://<내아이디>.github.io/2dWebFightGame/` 접속 가능

## 5. 플레이
1. 위 URL 접속 → **방 만들기** → 표시되는 링크를 친구에게 전송
2. 친구가 링크 접속 → 자동 참가 → 대전 시작!

## 주의사항
- **Render 무료 플랜은 15분 동안 접속이 없으면 잠들었다가 첫 접속 시 깨어나는 데
  30초~1분 걸린다.** 방이 안 만들어지면 잠시 기다렸다 새로고침.
- GitHub Pages는 https 이므로 서버 주소는 반드시 `wss://` (ws:// 는 브라우저가 차단).
- 서버 주소를 임시로 바꿔 테스트하려면 URL 뒤에 `?server=wss://...` 를 붙이면 된다.

## 보안 설정 (선택, 프로덕션 권장)
서버는 기본적으로 방/연결/메시지 폭주(DoS)를 막는 제한이 켜져 있다. Render 대시보드의
**Environment** 에서 아래 환경변수로 조정할 수 있다(모두 선택):

| 변수 | 기본값 | 설명 |
|------|:------:|------|
| `ALLOWED_ORIGINS` | (없음=모두 허용) | 접속 허용 사이트. 내 페이지로 제한 권장: `https://<내아이디>.github.io` |
| `MAX_ROOMS` | 500 | 동시 방 상한 |
| `MAX_CONNECTIONS` | 400 | 동시 연결 상한 |
| `MSG_RATE` | 120 | 연결당 초당 메시지 상한(초과 시 버리고, 지속되면 연결 종료) |

- `ALLOWED_ORIGINS` 를 설정하면 다른 웹사이트가 내 서버를 무단 사용하는 것을 막는다
  (여러 개는 쉼표로 구분). 미설정 시 모든 origin 허용 — 로컬 개발엔 편하지만
  공개 서버라면 설정을 권장.

## 로컬에서 온라인 대전 테스트
```bash
python server/server.py                    # 터미널 1: 대전 서버 (포트 8765)
python -m http.server 8080 -d docs        # 터미널 2: 웹 클라이언트
# 브라우저 탭 2개로 http://localhost:8080 접속 → 한쪽이 방 만들고 한쪽이 참가
```
