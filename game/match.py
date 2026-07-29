"""순수 게임 시뮬레이션 — 렌더링/입력장치/네트워크 무관.

데스크톱 클라이언트(game.py)와 온라인 대전 서버(server/server.py)가
같은 Match를 돌려서 로직이 한 곳에만 존재하게 한다.
"""

from . import settings as s
from .fighter import Fighter

# 눌림 상태로 전달되는 액션 목록 (이산 입력인 attack/방향 커맨드는 key_event로)
ACTIONS = ("left", "right", "jump", "down", "attack", "block")
NO_INPUT = {a: False for a in ACTIONS}


class Match:
    """한 매치(3판 2선승)의 전체 상태와 진행."""

    def __init__(self):
        self.frame = 0                    # 전역 프레임 카운터 (커맨드 타이밍 판정용)
        self.new_match()

    # ---- 초기화 (Setup) ----
    def new_match(self):
        """매치 전체(승수 포함) 초기화."""
        self.p1 = Fighter(
            x=s.WIDTH * 0.25 - s.FIGHTER_W / 2,
            color=s.P1_COLOR, accent=s.P1_ACCENT, facing=1, name="P1",
        )
        self.p2 = Fighter(
            x=s.WIDTH * 0.75 - s.FIGHTER_W / 2,
            color=s.P2_COLOR, accent=s.P2_ACCENT, facing=-1, name="P2",
        )
        self.wins = {"P1": 0, "P2": 0}
        self.match_over = False
        self.match_winner = None
        self.popup = None                 # (텍스트, 남은 프레임) - 특수기 명중 표시
        self.effects = []                 # 임팩트 스파크: [{x,y,life,max,big}]
        self.shake = 0                    # 화면 흔들림 남은 프레임
        self.hitstop = 0                  # 히트 시 정지 프레임 (타격감)
        self.start_round()

    def start_round(self):
        """한 라운드 초기화."""
        self.p1.reset(facing=1)
        self.p2.reset(facing=-1)
        self.round_frames = s.ROUND_TIME * s.FPS
        self.round_over = False
        self.round_winner = None          # "P1" / "P2" / "DRAW"
        self.round_end_delay = 0          # 라운드 종료 후 대기 프레임

    # ---- 입력 (Input) ----
    def key_event(self, side, action):
        """이산 키 입력(KEYDOWN 상당)을 해당 파이터에 전달."""
        if self.round_over or self.match_over:
            return
        fighter = self.p1 if side == "P1" else self.p2
        fighter.on_keydown(action, self.frame)

    # ---- 진행 (Step) ----
    def step(self, p1_actions, p2_actions):
        """한 프레임 진행. actions는 ACTIONS 키를 갖는 눌림 상태 딕셔너리."""
        # 히트스톱: 임팩트 순간 몇 프레임 완전 정지 (타격감)
        if self.hitstop > 0:
            self.hitstop -= 1
            return

        self.frame += 1

        # 팝업 수명 감소
        if self.popup:
            text, remain = self.popup
            self.popup = (text, remain - 1) if remain > 1 else None

        # 이펙트/흔들림 수명 감소 (라운드 종료·매치 종료 중에도 잔상은 사라지게)
        if self.shake > 0:
            self.shake -= 1
        if self.effects:
            for e in self.effects:
                e["life"] -= 1
            self.effects = [e for e in self.effects if e["life"] > 0]

        if self.match_over:
            return

        if self.round_over:
            # 라운드 종료 연출 후 다음 라운드/매치 정리
            self.round_end_delay -= 1
            if self.round_end_delay <= 0:
                self._advance_after_round()
            return

        # 입력
        self.p1.handle_input(p1_actions)
        self.p2.handle_input(p2_actions)

        # 물리 갱신
        self.p1.update()
        self.p2.update()

        # 착지·대시 먼지 (플래그는 읽고 나서 리셋)
        for p in (self.p1, self.p2):
            if p.just_landed or p.just_dashed:
                self._spawn_dust(p.center_x, s.GROUND_Y)
            p.just_landed = False
            p.just_dashed = False

        # 서로 바라보기
        self.p1.face(self.p2)
        self.p2.face(self.p1)

        # 겹침 방지 (간단한 밀어내기)
        self._resolve_overlap()

        # 공격 판정
        self._check_hit(self.p1, self.p2)
        self._check_hit(self.p2, self.p1)

        # 타이머
        self.round_frames -= 1

        # 라운드 종료 조건
        if self.p1.is_ko or self.p2.is_ko or self.round_frames <= 0:
            self._finish_round()

    def _resolve_overlap(self):
        a, b = self.p1, self.p2
        if a.rect.colliderect(b.rect):
            overlap = (a.rect.width - abs(a.center_x - b.center_x))
            push = max(1, overlap / 2)
            if a.center_x < b.center_x:
                a.x -= push
                b.x += push
            else:
                a.x += push
                b.x -= push
            a.x = max(0.0, min(a.x, s.WIDTH - s.FIGHTER_W))
            b.x = max(0.0, min(b.x, s.WIDTH - s.FIGHTER_W))

    def _check_hit(self, attacker, defender):
        hb = attacker.attack_hitbox()
        if hb and hb.colliderect(defender.rect):
            attacker.has_hit = True
            move = attacker.move

            # 반격기: 방어자가 반격 자세면 피해 무효 + 공격자에게 1.5배 반사
            if defender.counter_active:
                defender.counter_timer = 0                 # 반격 소비
                back = 1 if attacker.center_x >= defender.center_x else -1
                dmg = move["damage"] * s.COUNTER_MULT
                attacker.take_hit(dmg, back, 0, s.COUNTER_STUN, blocked=False)
                impact_x = attacker.x if back == -1 else attacker.x + s.FIGHTER_W
                impact_y = attacker.y + s.FIGHTER_H * 0.4
                self._spawn_spark(impact_x, impact_y, True, False)
                self.shake = max(self.shake, s.SHAKE_SPECIAL)
                self.hitstop = max(self.hitstop, s.HITSTOP_BIG)
                self.popup = (f"{defender.name} COUNTER!", s.FPS)
                return

            direction = 1 if defender.center_x >= attacker.center_x else -1
            blocked = self._is_blocked(move, defender)

            # 가드 브레이크: 가드 중 어퍼컷(guard_break 기술) 피격 → 가드 붕괴 + 1초 스턴
            if blocked and move.get("guard_break"):
                self._guard_break(attacker, defender, move, direction)
                return

            defender.take_hit(move["damage"], direction, move["launch"],
                              move.get("stun"), blocked)
            big = move is not s.NORMAL_MOVE and move["level"] != "low"
            # 임팩트 지점: 피격자의 맞은 쪽 옆면. 막았으면 가드 높이, 아니면 레벨별.
            impact_x = defender.x if direction == 1 else defender.x + s.FIGHTER_W
            impact_y = defender.y + s.FIGHTER_H * self._impact_frac(move["level"])
            self._spawn_spark(impact_x, impact_y, big and not blocked, blocked)
            if blocked:
                # 막으면 가드 게이지 소모 (압박). 소진되면 가드가 풀린다(잠금).
                defender.guard_gauge -= s.GUARD_CHIP
                if defender.guard_gauge <= 0:
                    defender.guard_gauge = 0
                    defender.guard_locked = True
                    defender.blocking = False
                self.shake = max(self.shake, s.SHAKE_NORMAL // 2)
                self.hitstop = max(self.hitstop, 2)
            else:
                self.shake = max(self.shake, s.SHAKE_SPECIAL if big else s.SHAKE_NORMAL)
                self.hitstop = max(self.hitstop, s.HITSTOP_BIG if big else s.HITSTOP)
            if move is not s.NORMAL_MOVE and move["level"] != "low":
                self.popup = (f"{attacker.name} {move['name']}!", s.FPS)

    def _guard_break(self, attacker, defender, move, direction):
        """가드 브레이크: 가드 붕괴, 관통 데미지, 1초 스턴, 전용 이펙트."""
        defender.blocking = False
        defender.guard_gauge = 0.0
        defender.guard_locked = True
        defender.guard_break_stun = s.GUARD_BREAK_STUN
        defender.attack_timer = 0
        defender.health = max(0.0, defender.health - move["damage"])
        defender.vx = direction * s.KNOCKBACK
        # 전용 이펙트 (히트 스파크와 구분되는 kind="guardbreak")
        bx = defender.x + (0 if direction == 1 else s.FIGHTER_W)
        by = defender.y + s.FIGHTER_H * 0.45
        self.effects.append({
            "x": int(bx), "y": int(by),
            "life": s.SPARK_LIFE_BIG, "max": s.SPARK_LIFE_BIG,
            "big": True, "block": False, "kind": "guardbreak",
        })
        self.shake = max(self.shake, s.SHAKE_SPECIAL)
        self.hitstop = max(self.hitstop, s.HITSTOP_BIG)
        self.popup = (f"{attacker.name} GUARD BREAK!", int(s.FPS * 1.2))

    @staticmethod
    def _is_blocked(move, defender):
        """공격 레벨 vs 방어 스탠스로 가드 성공 여부 판정.

        서서 막기(blocking, not crouch): mid/overhead 방어.
        앉아 막기(blocking + crouch):     low 방어.
        """
        if not defender.blocking:
            return False
        level = move["level"]
        if defender.crouching:
            return level == "low"
        return level in ("mid", "overhead")

    @staticmethod
    def _impact_frac(level):
        return {"low": 0.8, "overhead": 0.62}.get(level, 0.4)

    def _spawn_spark(self, x, y, big, blocked=False):
        self.effects.append({
            "x": int(x), "y": int(y),
            "life": s.SPARK_LIFE_BIG if big else s.SPARK_LIFE,
            "max": s.SPARK_LIFE_BIG if big else s.SPARK_LIFE,
            "big": big,
            "block": blocked,
            "kind": "spark",
        })

    def _spawn_dust(self, x, y):
        self.effects.append({
            "x": int(x), "y": int(y),
            "life": s.DUST_LIFE, "max": s.DUST_LIFE,
            "big": False, "block": False, "kind": "dust",
        })

    def _finish_round(self):
        self.round_over = True
        self.round_end_delay = int(s.FPS * 2.5)
        if self.p1.health > self.p2.health:
            self.round_winner = "P1"
        elif self.p2.health > self.p1.health:
            self.round_winner = "P2"
        else:
            self.round_winner = "DRAW"
        if self.round_winner in ("P1", "P2"):
            self.wins[self.round_winner] += 1

    def _advance_after_round(self):
        if self.wins["P1"] >= s.ROUNDS_TO_WIN:
            self.match_over = True
            self.match_winner = "P1"
        elif self.wins["P2"] >= s.ROUNDS_TO_WIN:
            self.match_over = True
            self.match_winner = "P2"
        else:
            self.start_round()

    # ---- 직렬화 (Serialization) ----
    def state(self):
        """웹 클라이언트로 보낼 JSON 직렬화 가능한 상태 스냅샷."""
        return {
            "fighters": [
                {
                    "name": f.name,
                    "health": f.health,
                    **f.render_state(),
                }
                for f in (self.p1, self.p2)
            ],
            "wins": self.wins,
            "time": max(0, self.round_frames // s.FPS),
            "round_over": self.round_over,
            "round_winner": self.round_winner,
            "match_over": self.match_over,
            "match_winner": self.match_winner,
            "popup": self.popup[0] if self.popup else None,
            "effects": [
                {"x": e["x"], "y": e["y"], "t": e["life"] / e["max"],
                 "big": e["big"], "block": e["block"], "kind": e.get("kind", "spark")}
                for e in self.effects
            ],
            "shake": self.shake,
        }
