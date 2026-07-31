# 배포 가이드 — URL로 바로 온라인 대전

목표: 친구에게 링크만 보내면 브라우저에서 바로 대전.
구성: **클라이언트 = GitHub Pages** (정적) + **서버 = 집 NAS 의 Docker 컨테이너** (WebSocket).

## 0. 준비물
- GitHub 계정 (https://github.com)
- Docker 를 돌릴 수 있는 NAS (여기선 Portainer + DSM 역방향 프록시)

## 1. GitHub에 올리기
로컬 커밋은 이미 되어 있다. GitHub에서 새 저장소를 만들고 push:

```bash
# GitHub에서 새 저장소(예: 2dWebFightGame)를 만든 뒤:
git remote add origin https://github.com/<내아이디>/2dWebFightGame.git
git push -u origin main
```

## 2. 서버 배포 (NAS Docker) — 현재 구성

전제(확인된 상태): NAS 의 DSM nginx 가 443 에서 **`creamel.duckdns.org` 용 Let's Encrypt
인증서**를 서비스 중이다. 그래서 **새 인증서 발급 없이**
443 에 경로 하나(`/fight`)만 얹으면 `wss://creamel.duckdns.org/fight` 로 붙는다.
(`nas.creamel.kr` 은 같은 IP 지만 이 인증서에 포함되어 있지 않으므로 wss 주소로 쓰지 말 것.)

### 1) 이미지 빌드는 GitHub 이 한다
main 에 push 되면 [.github/workflows/docker-image.yml](.github/workflows/docker-image.yml) 이
이미지를 빌드해 **`ghcr.io/mincheolj539-dot/fight-server:latest`** 로 올린다.
NAS 는 빌드 없이 pull 만 하면 된다.

현재 이 패키지는 **익명 pull 가능**(공개) 상태다 — NAS 에서 별도 로그인이 필요 없다.
혹시 private 으로 바뀌면 GitHub → 프로필 → **Packages → fight-server →
Package settings → Change visibility → Public** 으로 되돌리면 된다.

### 2) 컨테이너 띄우기 (DSM Container Manager)
DSM → **Container Manager → 프로젝트 → 생성**

- 경로: 아무 폴더나 새로 지정(예: `/docker/fight-server`)
- 소스: **YAML 붙여넣기** → [docker-compose.yml](docker-compose.yml) 내용 그대로
- 다음 → 완료 (이미지 pull 후 자동 실행)

> Portainer 를 쓸 수도 있지만, 환경이 Edge Agent 로 등록돼 있고 연결이 끊긴 상태라면
> 에이전트를 NAS 에 다시 띄워야 하므로 Container Manager 쪽이 빠르다.

확인 — NAS 안에서(또는 Container Manager 로그에서):
```bash
curl http://localhost:8765          # → "fight server OK"
```

레이팅 기록은 컨테이너 안 `/app/data/ratings.json` 에 쌓이고, compose 의 `fight-data`
볼륨에 보존된다(컨테이너를 지우고 다시 만들어도 점수가 남는다). 초기화하려면 그 볼륨을 삭제.

코드를 고친 뒤 서버를 갱신하려면: main 에 push → Actions 완료 후
Container Manager 프로젝트에서 **재빌드/다시 시작**(이미지 pull) 하면 된다.

### 3) 역방향 프록시로 wss 열기 (DSM)
DSM → **제어판 → 로그인 포털 → 고급 → 역방향 프록시 → 생성**

| 항목 | 값 |
|------|-----|
| 소스 프로토콜 / 호스트 이름 / 포트 | HTTPS / `creamel.duckdns.org` / `443` |
| 소스 경로 | `/fight` |
| 대상 프로토콜 / 호스트 이름 / 포트 | HTTP / `localhost` / `8765` |

**사용자 지정 헤더** 탭에서 `WebSocket` 프리셋을 추가한다(= `Upgrade`, `Connection` 헤더).
이걸 빠뜨리면 핸드셰이크가 400/502 로 실패한다. 서버는 경로를 보지 않으므로
`/fight` 를 그대로 넘겨도 된다.

443 은 이미 외부에 열려 있으므로 라우터 포트포워딩은 추가할 것이 없다.

### 4) 확인
```bash
curl https://creamel.duckdns.org/fight
```
`fight server OK` 가 나오면 프록시가 서버까지 닿은 것(서버는 웹소켓이 아닌 요청에 이렇게 답한다).
그다음 브라우저에서 `?server=wss://creamel.duckdns.org/fight` 를 붙여 열고
**방 만들기** 가 되면 웹소켓 업그레이드까지 성공.

### 주의
- NAS 가 꺼지거나 인터넷이 끊기면 온라인 대전도 멈춘다(대신 콜드 스타트는 없다).
- duckdns 인증서 갱신은 DSM 이 자동으로 한다. 만료되면 wss 가 바로 끊기니 갱신 실패 알림을 켜둘 것.
- 집 IP 가 바뀌어도 duckdns 가 따라가지만, `nas.creamel.kr` A 레코드는 수동 관리라면 같이 갱신해야 한다.

## 3. 클라이언트에 서버 주소 연결
[docs/config.js](docs/config.js) 의 `PROD` 가 서버 주소다. 현재 값:

```js
var PROD = "wss://creamel.duckdns.org/fight";
```

주소를 바꿨으면 커밋 후 push(= GitHub Pages 재배포):

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
- **서버(NAS 컨테이너)가 떠 있어야 온라인 대전이 된다.** 방이 안 만들어지면
  Portainer 에서 `fight-server` 컨테이너 상태부터 확인.
- GitHub Pages는 https 이므로 서버 주소는 반드시 `wss://` (ws:// 는 브라우저가 차단).
- 서버 주소를 임시로 바꿔 테스트하려면 URL 뒤에 `?server=wss://...` 를 붙이면 된다.

## 보안 설정 (선택, 프로덕션 권장)
서버는 기본적으로 방/연결/메시지 폭주(DoS)를 막는 제한이 켜져 있다.
[docker-compose.yml](docker-compose.yml) 의 `environment:` 에서 아래 값을 조정한다(모두 선택):

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
`docs/config.js` 는 **localhost 로 열면 자동으로 `ws://localhost:8765`** 를,
배포 사이트에서 열면 프로덕션(`wss://...`) 주소를 쓴다. 따라서 로컬 테스트에
`?server=` 를 붙일 필요가 없고, 배포 서버가 죽어 있어도 로컬 대전은 된다.
