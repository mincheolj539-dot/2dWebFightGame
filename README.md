# 2D Web Fight Game

Python(Pygame) 으로 만든 2D 격투 게임. 두 가지 방식으로 플레이할 수 있다:

1. **온라인 대전** — 브라우저에서 URL 접속, 방 만들고 링크 공유하면 친구와 대전
2. **로컬 대전** — 데스크톱에서 한 키보드로 2인 플레이

## 특징
- 온라인 대전 (방 코드/링크 공유, 서버 권위 시뮬레이션 — 게임 로직은 전부 Python)
- 3판 2선승제, 체력바, 라운드 타이머
- 이동 / 점프 / 중력, 공격(히트박스), 방어(가드), 넉백, 피격 경직
- 철권식 커맨드 특수기 (대시 펀치, 어퍼컷)
- 외부 에셋 없이 도형 렌더링으로 즉시 실행

## 설치 (Setup)
```bash
pip install -r requirements.txt
```

## 온라인 대전 (Online play)
호스팅(무료) 방법은 **[DEPLOY.md](DEPLOY.md)** 참고. 로컬 테스트:
```bash
python server/server.py               # 터미널 1: 대전 서버
python -m http.server 8080 -d docs    # 터미널 2: 웹 클라이언트
# 브라우저 탭 2개로 http://localhost:8080 접속
```

## 로컬 대전 (Desktop, 한 키보드 2인)
```bash
python main.py
```

## 조작법 (Controls)

|        | 이동 (Move) | 점프 (Jump) | 아래 (Down) | 공격 (Attack) | 방어 (Block) |
|--------|:-----------:|:-----------:|:-----------:|:-------------:|:------------:|
| **P1** | A / D       | W           | S           | F             | G            |
| **P2** | ← / →       | ↑           | ↓           | . (period)    | / (slash)    |

- **R** : 매치 재시작 (restart match)
- **Esc** / 창 닫기 : 종료 (quit)

## 커맨드 기술 (Special Moves)

방향을 순서대로 입력한 뒤 공격 키를 누르면 특수기가 나간다. (철권식 커맨드)
방향은 **바라보는 방향 기준**이다 — `앞` = 상대 쪽.

| 기술 | 커맨드 | 효과 |
|------|--------|------|
| **대시 펀치** (DASH PUNCH) | 앞, 앞 + 공격 | 돌진하며 강한 펀치 (데미지 16) |
| **어퍼컷** (UPPERCUT) | ↓, 앞 + 공격 | 상대를 공중에 띄움 (데미지 14) |

예) P1이 오른쪽을 보고 있을 때: `D D F` = 대시 펀치, `S D F` = 어퍼컷.
커맨드는 약 0.6초(35프레임) 안에 입력해야 성립한다. 기술 값 조정은 `game/settings.py`의 `SPECIAL_MOVES`.

## 구조 (Structure)
```
main.py            # 데스크톱 진입점
game/
  settings.py      # 상수 / 색상 / 물리 / 전투 / 기술 정의
  fighter.py       # Fighter (상태머신 · 물리 · 전투 · 커맨드)
  match.py         # Match (순수 시뮬레이션 — 데스크톱·서버 공유)
  game.py          # 데스크톱 렌더링 + 로컬 입력
server/
  server.py        # 온라인 대전 WebSocket 서버 (Match를 60Hz 실행)
docs/              # 브라우저 클라이언트 (GitHub Pages 호스팅용)
  index.html / game.js / config.js
render.yaml        # Render 서버 배포 설정
DEPLOY.md          # 배포 가이드
```

## 참고
- 온라인 대전은 서버가 게임을 계산하고 브라우저는 그리기만 한다 (치트 불가).
- 조작 값·데미지·기술 등 모든 밸런스 상수는 `game/settings.py` 에 모여 있다.
  새 특수기는 `SPECIAL_MOVES` 리스트에 항목 하나만 추가하면 된다.
