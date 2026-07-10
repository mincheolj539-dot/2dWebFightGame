# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python(Pygame-ce) 로 만든 2D 격투 게임. 두 실행 모드: ① 데스크톱 로컬 2인 대전(`main.py`), ② **온라인 대전** — WebSocket 서버(`server/`)가 게임을 시뮬레이션하고 브라우저 클라이언트(`docs/`, GitHub Pages 호스팅)가 렌더링. 외부 에셋 없이 도형만으로 렌더링. 철권식 커맨드 입력(방향 연속 입력 + 공격)으로 특수기 발동.

## Commands

```bash
pip install -r requirements.txt        # 의존성 (pygame-ce, pygbag)
python main.py                         # 데스크톱 로컬 2인 대전
python server/server.py                # 온라인 대전 서버 (포트 8765, PORT env로 변경)
python -m http.server 8080 -d docs     # 웹 클라이언트 서빙 → 탭 2개로 온라인 대전 테스트
```

배포는 [DEPLOY.md](DEPLOY.md): 클라이언트 = GitHub Pages(main 브랜치 /docs), 서버 = Render(render.yaml). `docs/config.js` 의 `GAME_SERVER` 가 서버 주소.

테스트 프레임워크는 없다. 로직 검증은 SDL dummy 드라이버로 창 없이 돌리는 헤드리스 스모크 테스트로 한다:

```python
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame; pygame.init()
from game.game import Game
# FakeKeys(__getitem__로 키셋 조회)로 g.update(keys)를 프레임 단위 호출.
# 이산 입력(공격/커맨드)은 fighter.on_keydown(key, frame)을 직접 호출해 시뮬레이션.
# g.p2.health 변화, g.wins, g.match_over 검사. g.round_frames=1 로 타임아웃 경로 강제 가능.
```

## Architecture

**핵심 원칙: 게임 로직은 `game/match.py`의 `Match` 한 곳에만 존재한다.** 데스크톱(`game/game.py`)과 온라인 서버(`server/server.py`)가 같은 Match를 돌리고, 브라우저(`docs/game.js`)는 서버가 보낸 상태를 그리는 "얇은 렌더러"다. 게임플레이를 바꿀 때 JS를 수정할 일은 거의 없어야 정상 — JS에 로직이 생기면 잘못된 방향.

- **`game/match.py` — `Match`** — 순수 시뮬레이션 (렌더링/입력장치/네트워크 무관).
  - 라운드 흐름: `new_match()`(승수 초기화) → `start_round()` → `step(p1_actions, p2_actions)` → `_finish_round()` → `round_end_delay` 카운트다운 → `_advance_after_round()`. 3판 2선승제(`ROUNDS_TO_WIN`).
  - **공격 판정은 Match가 중재**: `_check_hit()` 가 `attack_hitbox()` 와 `rect` 충돌 검사 후 `attacker.move` 의 데미지/launch 로 `take_hit()` 호출. 다단히트는 `has_hit` 플래그로 방지.
  - `state()` 가 JSON 직렬화 가능한 스냅샷 반환 — 서버가 매 프레임 브로드캐스트.

- **입력은 이중 경로다 — 혼동 주의**:
  - **눌림 상태** (`step()` 의 actions 딕셔너리): 이동/점프/방어. 매 프레임 연속 적용.
  - **이산 입력** (`key_event(side, action)` → `fighter.on_keydown`): 커맨드 버퍼 기록과 공격 발동. 커맨드 판정에는 "언제 눌렀는가"가 필요하므로 폴링으로 옮기면 안 된다. (웹 클라이언트도 `e.repeat` 를 걸러서 보낸다.)
  - 커맨드 흐름: 방향 입력 → facing 기준 상대 방향 토큰(`forward/back/down`)으로 `input_buffer` 에 기록 → 공격 시 `_try_attack` 이 `SPECIAL_MOVES` 의 seq 를 최근 `COMMAND_WINDOW` 프레임과 대조 → 매치되면 특수기, 아니면 `NORMAL_MOVE`. 발동 시 버퍼를 비운다.

- **`game/fighter.py` — `Fighter`** — 상태머신·물리·전투. P1/P2 동일 클래스. 입력은 pygame 키가 아닌 **액션 이름**("left"/"attack" 등)으로 받는다 — 키 → 액션 변환은 클라이언트(game.py의 CONTROLS, docs/game.js의 KEYMAP) 담당.
  - `render_state()` 가 그리기 도형(fist/guard/eye/flash 좌표)을 계산하는 **단일 출처** — 데스크톱 `draw()` 와 웹 전송 상태가 모두 이걸 쓴다. 외형 로직을 JS에 중복 구현하지 말 것.

- **`server/server.py`** — websockets 기반 방(room) 서버. 방마다 Match를 60Hz로 실행(서버 권위 — 클라이언트는 입력만 전송). 프로토콜(JSON)은 파일 상단 docstring 참고. 브로드캐스트는 논블로킹 `websockets.asyncio.server.broadcast` 사용 — `await ws.send()` 루프로 바꾸면 느린 클라이언트가 방 전체를 멈춘다. 인터넷 노출 서버라 DoS 방어(방/연결/메시지 상한·레이트리밋·`max_size`·Origin 검사, 상단 상수·env로 조정)를 둔다. **연결 핸들러는 반드시 모든 예외를 격리**(`except Exception`)해야 한다 — 한 연결의 오류(과대 메시지 등)가 새어나가면 서버가 새 연결을 못 받는 상태로 망가진다.

- **`game/game.py` + `main.py`** — 데스크톱 클라이언트(렌더링 + 키 변환 + async 루프). `await asyncio.sleep(0)` 는 Pygbag 호환 잔재이자 관례로 유지.

- **`docs/`** — GitHub Pages 용 정적 클라이언트. `game.js` 상단 상수(캔버스 크기·색상·`HIT_STUN`/`SHAKE_*`)만 `settings.py` 와 수동 동기화 — 값을 바꾸면 양쪽 다 수정할 것. `index.html` 의 `?v=N` 캐시버스터는 `game.js`/`config.js` 를 수정할 때마다 숫자를 올려 플레이어의 브라우저가 옛 JS를 캐시하지 않게 한다.
  - 히트 이펙트(임팩트 스파크·화면 흔들림·피격 광선)는 `Match` 가 `state()`(effects/shake) 와 fighter의 `hurt` 로 데이터를 내려주고, `game.py`/`game.js` 두 렌더러가 동일하게 그린다. 흔들림은 월드(배경+파이터+스파크)에만 적용하고 HUD/오버레이는 고정.

- **`game/settings.py`** — **모든 밸런스·색상·물리 상수의 단일 출처**. 기술 정의(`NORMAL_MOVE`, `CROUCH_MOVE`, `AIR_MOVE`, `SPECIAL_MOVES` — 각 dict에 damage/range/duration/active/cooldown/lunge/launch/stun/**level**)를 포함. 새 특수기 추가 = `SPECIAL_MOVES` 에 dict 하나 추가로 끝나야 정상 (서버·데스크톱 자동 반영, JS 수정 불필요).

- **반격기(Counter)** — 지상에서 **방어(G) 홀드 중 공격(F)** 으로 발동(`Fighter._start_counter`). 히트박스 없는 반격 자세(`counter_timer`, 0.5초)에 진입하고, 그 안에 맞으면 `Match._check_hit` 이 피해를 무효화하고 공격자에게 `COUNTER_MULT`(1.5)배를 반사한다. 발동 중 금색 오라로 표시(`render_state`의 `counter` 필드). 창이 아무도 안 맞고 만료되면(헛방) `Fighter.update` 가 `COUNTER_FAIL_STUN` 경직을 자신에게 건다(hitstun 재사용). 재사용 쿨타임은 `counter_cd`(창+`COUNTER_COOLDOWN`).

- **스탠스 & 공격 레벨(철권식 이지선다)** — 공격은 컨텍스트로 선택된다(`Fighter._try_attack`): 방어 홀드 중→반격 자세, 공중→`AIR_MOVE`(점프킥), 커맨드 매치→특수기, 아래 홀드→`CROUCH_MOVE`(로우킥), 그 외→`NORMAL_MOVE`. 각 move의 `level`(mid/low/overhead)과 방어자 스탠스로 가드 성패를 `Match._is_blocked` 가 판정: 서서 막기=mid·overhead 방어, 앉아 막기=low 방어. 웅크리기(`crouching`, 아래 홀드+지상)는 걷기/점프를 막고 몸통 높이를 줄인다(`CROUCH_H`). 히트박스 y와 그리기 박스(`bx/by/bw/bh`)는 레벨·크라우치에 따라 `attack_hitbox`/`render_state` 가 계산한다.

## Conventions

- 코드 주석은 한국어(설명) + 필요 시 영어 병기 스타일을 따른다.
- 좌표/속도는 float 로 다루고 렌더/Rect 생성 시 `int()` 로 변환한다. facing 은 `1`(오른쪽)/`-1`(왼쪽). 커맨드 방향은 절대 방향이 아니라 facing 기준 상대 방향이다.
- 새 상수는 매직 넘버로 코드에 박지 말고 `settings.py` 에 추가한다.

---

# Behavioral Guidelines (from andrej-karpathy-skills)

Source: https://github.com/multica-ai/andrej-karpathy-skills

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
