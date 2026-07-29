"""파이터(캐릭터) 클래스 — 상태머신, 물리, 전투 로직.

입력은 pygame 키가 아니라 액션 이름("left"/"right"/"jump"/"down"/"attack"/"block")으로
받는다. 키 → 액션 변환은 로컬 클라이언트(game.py)나 서버가 담당하므로,
이 클래스는 데스크톱/서버 어디서든 동일하게 동작한다.
"""

import math

import pygame

from . import settings as s


class Fighter:
    """한 명의 격투가. P1/P2 모두 같은 클래스를 재사용한다."""

    def __init__(self, x, color, accent, facing, name):
        self.spawn_x = x
        self.color = color
        self.accent = accent
        self.name = name
        self.reset(facing)

    def reset(self, facing):
        """라운드 시작 시 상태 초기화."""
        self.x = float(self.spawn_x)
        self.y = float(s.GROUND_Y - s.FIGHTER_H)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = facing              # 1 = 오른쪽, -1 = 왼쪽
        self.health = s.MAX_HEALTH
        self.on_ground = True
        self.attack_timer = 0             # 공격 애니메이션 진행 프레임
        self.cooldown = 0                 # 공격 후 재입력 대기
        self.hitstun = 0                  # 피격 경직
        self.blocking = False
        self.crouching = False            # 웅크리기 (아래 홀드, 지상)
        self.holding_down = False         # 아래 키 눌림 상태 (공격 시 로우킥 판정용)
        self.guard_gauge = float(s.GUARD_MAX)  # 가드 게이지 (0이면 가드 불가)
        self.guard_locked = False         # 게이지 소진으로 가드 잠김 (회복 대기)
        self.guard_cd = 0                 # 가드 해제 후 재가드 쿨타임 (연타 방지)
        self.was_blocking = False         # 직전 프레임 방어 여부 (해제 감지용)
        self.guard_break_stun = 0         # 가드 브레이크 스턴 남은 프레임
        self.counter_timer = 0            # 반격 자세 남은 프레임 (>0이면 반격 판정)
        self.counter_cd = 0               # 반격 재사용 쿨타임 남은 프레임
        self.dash_timer = 0               # 대시 남은 프레임 (>0이면 대시 이동 중)
        self.dash_vx = 0.0                # 대시 속도 (절대 방향)
        self.has_hit = False              # 이번 공격이 이미 명중했는지 (다단히트 방지)
        self.move = s.NORMAL_MOVE         # 현재/마지막 시전한 기술
        self.input_buffer = []            # [(frame, token)] - 커맨드 판정용 최근 방향 입력
        self.anim_t = 0                   # 애니메이션 프레임 카운터 (걷기/대기 사이클)

    # ---- 파생 속성 (Derived properties) ----
    @property
    def rect(self):
        """몸통 히트박스 (피격 판정 대상)."""
        return pygame.Rect(int(self.x), int(self.y), s.FIGHTER_W, s.FIGHTER_H)

    @property
    def center_x(self):
        return self.x + s.FIGHTER_W / 2

    @property
    def is_ko(self):
        return self.health <= 0

    @property
    def is_attacking(self):
        return self.attack_timer > 0

    @property
    def counter_active(self):
        return self.counter_timer > 0

    # ---- 입력 (Input) ----
    def handle_input(self, actions):
        """눌림 상태 액션 딕셔너리로 이동/점프/방어/웅크리기를 처리한다 (연속 입력)."""
        self.holding_down = actions["down"]

        # 경직/가드브레이크 스턴/KO면 입력 무시 (가드 게이지는 회복만)
        if self.hitstun > 0 or self.guard_break_stun > 0 or self.is_ko:
            self.blocking = False
            self.crouching = False
            self.was_blocking = False
            self._regen_guard()
            return

        # 대시 중이면 대시 속도로 이동 (공격 중이 아닐 때). 걷기/방어/웅크리기 무시.
        if self.dash_timer > 0 and not self.is_attacking:
            self.vx = self.dash_vx
            self.blocking = False
            self.crouching = False
            return

        moving = False

        # 웅크리기: 지상에서 아래 홀드. 로우킥(CROUCH_MOVE) 중에도 자세 유지.
        # (다른 지상 공격 중에는 일어선다)
        self.crouching = (
            actions["down"] and self.on_ground
            and (not self.is_attacking or self.move is s.CROUCH_MOVE)
        )

        # 방어(가드 게이지): 게이지가 있고 잠기지 않고 쿨타임이 아닐 때만 가드 가능.
        # 홀드하면 게이지가 닳고, 소진되면 가드가 풀린다. 뗀 직후엔 잠깐 재가드 불가(연타 방지).
        want_block = actions["block"] and self.on_ground
        self.blocking = (want_block and self.guard_gauge >= 1
                         and not self.guard_locked and self.guard_cd == 0)
        if self.blocking:
            self.guard_gauge -= s.GUARD_DRAIN
            if self.guard_gauge <= 0:          # 게이지 소진 → 가드 풀림 + 잠금
                self.guard_gauge = 0
                self.guard_locked = True
                self.blocking = False
        else:
            self._regen_guard()
        if self.was_blocking and not self.blocking:   # 가드 해제 → 재가드 쿨타임
            self.guard_cd = s.GUARD_RELEASE_CD
        self.was_blocking = self.blocking

        if not self.blocking and not self.crouching and not self.is_attacking:
            if actions["left"]:
                self.vx = -s.MOVE_SPEED
                moving = True
            if actions["right"]:
                self.vx = s.MOVE_SPEED
                moving = True

        # 공격 중(돌진 특수기)이거나 공중이면 vx 유지 (관성/lunge 보존)
        if not moving and self.on_ground and not self.is_attacking:
            self.vx = 0.0

        # 점프 (웅크리는 중엔 불가)
        if actions["jump"] and self.on_ground and not self.blocking and not self.crouching:
            self.vy = s.JUMP_VELOCITY
            self.on_ground = False

        # 공격은 이산 입력(on_keydown)에서 처리한다.
        # 커맨드(연속 방향 입력) 판정에는 눌림 상태가 아니라 이산 입력이 필요하기 때문.

    def _regen_guard(self):
        """가드 게이지 회복. 소진 잠금은 충분히 회복되면 해제."""
        self.guard_gauge = min(float(s.GUARD_MAX), self.guard_gauge + s.GUARD_REGEN)
        if self.guard_locked and self.guard_gauge >= s.GUARD_RECOVER:
            self.guard_locked = False

    # ---- 커맨드 입력 (Command inputs) ----
    def on_keydown(self, action, frame):
        """이산 키 입력 1회를 처리. 방향은 버퍼에 기록, 공격은 기술 발동 시도."""
        if action == "attack":
            self._try_attack(frame)
            return
        # 방향 입력을 facing 기준 상대 방향 토큰으로 변환 (철권식 커맨드는 방향 상대적)
        if action == "left":
            token = "back" if self.facing == 1 else "forward"
        elif action == "right":
            token = "forward" if self.facing == 1 else "back"
        elif action == "down":
            token = "down"
        else:
            return                        # jump/block 등은 커맨드에 쓰지 않음
        self.input_buffer.append((frame, token))
        del self.input_buffer[:-s.BUFFER_SIZE]
        # 대시: 같은 방향(앞/뒤) 2연타 → 대시 이동
        if token in ("forward", "back"):
            self._check_dash(frame, token)

    def _check_dash(self, frame, token):
        """같은 방향 2연타면 그 방향으로 대시 (지상, 공격/반격/경직 중 제외)."""
        if (not self.on_ground or self.is_attacking or self.hitstun > 0
                or self.counter_active):
            return
        if self._buffer_ends_with((token, token), frame):
            self.dash_timer = s.DASH_DURATION
            direction = self.facing if token == "forward" else -self.facing
            self.dash_vx = direction * s.DASH_SPEED
            self.input_buffer.clear()     # 3연타로 재발동되지 않게

    def _try_attack(self, frame):
        """상황(방어중/공중/앉기/커맨드)에 맞는 기술을 골라 시전한다.

        우선순위:
          1) 지상 방어 홀드 중 공격 → 반격기 (공격 F + 방어 G 동시)
          2) 공중               → 점프킥 (오버헤드)
          3) 커맨드 매치         → 특수기 (어퍼컷 등, 아래를 눌러도 커맨드가 우선)
          4) 아래 홀드           → 로우킥
          5) 그 외               → 기본 펀치
        """
        if (self.hitstun > 0 or self.guard_break_stun > 0 or self.is_ko
                or self.is_attacking or self.cooldown > 0):
            return
        if self.counter_active:           # 이미 반격 자세면 재입력 무시
            return

        # 반격기: 지상에서 방어(G) 홀드 중 공격(F) → 히트박스 없는 반격 자세
        # 쿨타임 중에는 발동되지 않는다.
        if self.on_ground and self.blocking:
            if self.counter_cd == 0:
                self._start_counter()
            return

        if not self.on_ground:
            move = s.AIR_MOVE
        else:
            move = None
            for special in s.SPECIAL_MOVES:
                if self._buffer_ends_with(special["seq"], frame):
                    move = special
                    break
            if move is None:
                move = s.CROUCH_MOVE if self.holding_down else s.NORMAL_MOVE

        self.move = move
        self.attack_timer = move["duration"]
        self.cooldown = move["duration"] + move["cooldown"]
        self.has_hit = False
        if self.on_ground:                # 공중에선 관성 유지 (lunge 미적용)
            self.vx = self.facing * move["lunge"]
        self.input_buffer.clear()         # 같은 입력으로 연속 발동 방지

    def _start_counter(self):
        """반격 자세 진입 (히트박스 없음). 0.5초 안에 맞으면 Match가 반격 처리.

        쿨타임은 창 종료 후에도 이어지도록 창+쿨타임 길이로 잡는다.
        창이 만료될 때까지 아무도 안 맞으면 update()에서 실패 스턴을 건다.
        """
        self.counter_timer = s.COUNTER_WINDOW
        self.counter_cd = s.COUNTER_WINDOW + s.COUNTER_COOLDOWN
        self.vx = 0.0
        self.input_buffer.clear()

    def _buffer_ends_with(self, seq, frame):
        """최근 COMMAND_WINDOW 프레임 내 방향 입력이 seq로 끝나는지 검사."""
        recent = [t for f, t in self.input_buffer if frame - f <= s.COMMAND_WINDOW]
        return tuple(recent[-len(seq):]) == tuple(seq)

    # ---- 상태 갱신 (Update) ----
    def update(self):
        self.anim_t += 1
        # 중력
        self.vy += s.GRAVITY
        self.x += self.vx
        self.y += self.vy

        # 바닥 충돌
        floor = s.GROUND_Y - s.FIGHTER_H
        if self.y >= floor:
            self.y = float(floor)
            self.vy = 0.0
            self.on_ground = True

        # 화면 경계 (Clamp to screen)
        self.x = max(0.0, min(self.x, s.WIDTH - s.FIGHTER_W))

        # 타이머 감소
        if self.attack_timer > 0:
            self.attack_timer -= 1
        if self.dash_timer > 0:
            self.dash_timer -= 1
        if self.counter_cd > 0:
            self.counter_cd -= 1
        if self.counter_timer > 0:
            self.counter_timer -= 1
            # 반격 성공은 Match가 counter_timer를 즉시 0으로 만든다.
            # 여기서 0에 도달했다면 = 아무도 안 맞음 = 반격 실패 → 자신이 경직.
            if self.counter_timer == 0:
                self.hitstun = max(self.hitstun, s.COUNTER_FAIL_STUN)
        if self.cooldown > 0:
            self.cooldown -= 1
        if self.guard_cd > 0:
            self.guard_cd -= 1
        if self.guard_break_stun > 0:
            self.guard_break_stun -= 1
        if self.hitstun > 0:
            self.hitstun -= 1
            # 경직 중 넉백 감쇠
            self.x += self.vx
            self.x = max(0.0, min(self.x, s.WIDTH - s.FIGHTER_W))
            self.vx *= 0.8

    def face(self, opponent):
        """항상 상대를 바라보도록 방향 갱신 (공중/공격/경직 중에는 고정)."""
        if (self.on_ground and not self.is_attacking
                and self.hitstun == 0 and self.guard_break_stun == 0):
            self.facing = 1 if opponent.center_x >= self.center_x else -1

    # ---- 전투 (Combat) ----
    def attack_hitbox(self):
        """공격 활성 프레임 동안만 주먹 히트박스를 반환. 아니면 None."""
        if not self.is_attacking or self.has_hit:
            return None
        m = self.move
        elapsed = m["duration"] - self.attack_timer
        if not (m["active"][0] <= elapsed <= m["active"][1]):
            return None
        reach = m["range"]
        level = m["level"]
        if m["launch"]:
            # 어퍼컷: 몸통 위쪽까지 세로로 긴 히트박스
            h = int(s.FIGHTER_H * 0.6)
            y = int(self.y)
        elif level == "low":
            # 로우킥: 발밑 근처
            h = 24
            y = int(self.y + s.FIGHTER_H * 0.78)
        elif level == "overhead":
            # 점프킥: 아래로 뻗는 발 (공중에서 내려찍기)
            h = 46
            y = int(self.y + s.FIGHTER_H * 0.5)
        else:
            h = 24
            y = int(self.y + s.FIGHTER_H * 0.35)
        if self.facing == 1:
            x = int(self.x + s.FIGHTER_W)
        else:
            x = int(self.x - reach)
        return pygame.Rect(x, y, reach, h)

    def take_hit(self, damage, knockback_dir, launch=0, stun=None, blocked=False):
        """피격 처리. blocked=True면 데미지/넉백 경감(가드). launch면 공중으로 띄움.

        blocked 여부는 공격 레벨 vs 방어 스탠스로 Match가 판정해 넘긴다.
        stun: 피격 경직 프레임 (기술별 지정, 기본 HIT_STUN).
        """
        if self.is_ko:
            return
        stun = s.HIT_STUN if stun is None else stun
        if blocked:
            self.health -= damage * s.BLOCK_DAMAGE_MULT
            self.vx = knockback_dir * (s.KNOCKBACK * 0.4)
            self.hitstun = max(self.hitstun, stun // 2)
        else:
            self.health -= damage
            self.vx = knockback_dir * s.KNOCKBACK
            self.hitstun = stun
            self.attack_timer = 0
            if launch:
                self.vy = float(launch)
                self.on_ground = False
        self.health = max(0.0, self.health)

    # ---- 렌더 상태 (Render state) ----
    def render_state(self):
        """그리기에 필요한 도형 정보를 계산해 반환.

        데스크톱 draw()와 웹 클라이언트(JSON 전송)가 공유하는 단일 출처 —
        외형 계산 로직을 JS에 중복 구현하지 않기 위함.
        """
        # 몸통 그리기 박스 (웅크리면 높이가 줄고 발은 바닥에 유지)
        bh = s.CROUCH_H if self.crouching else s.FIGHTER_H
        by = int(self.y + (s.FIGHTER_H - bh))
        st = {
            "x": int(self.x),
            "y": int(self.y),
            "bx": int(self.x), "by": by, "bw": s.FIGHTER_W, "bh": bh,
            "crouch": self.crouching,
            "facing": self.facing,
            "flash": self.hitstun > 0 and (self.hitstun // 2) % 2 == 0,
            "hurt": max(0, self.hitstun),   # 피격 경직 남은 프레임 (내리쬐는 광선 강도)
            "counter": max(0, self.counter_timer),  # 반격 자세 남은 프레임 (>0이면 빛남)
            "guard_gauge": max(0.0, self.guard_gauge / s.GUARD_MAX),  # 0..1 (HUD 바)
            "guard_locked": self.guard_locked,
            "guard_break": max(0, self.guard_break_stun),  # 가드 브레이크 스턴 남은 프레임
            "eye": (int(self.center_x + self.facing * 12), by + int(bh * 0.30)),
            "fist": None,
            "guard": None,
        }
        if self.is_attacking:
            m = self.move
            elapsed = m["duration"] - self.attack_timer
            active = m["active"][0] <= elapsed <= m["active"][1]
            reach = m["range"] if active else m["range"] // 2
            lvl = m["level"]
            if m["launch"]:
                arm_y = int(self.y + s.FIGHTER_H * 0.5 - elapsed * 4)  # 어퍼컷 상승 궤적
            elif lvl == "low":
                arm_y = int(self.y + s.FIGHTER_H * 0.82)              # 로우킥 발밑
            elif lvl == "overhead":
                arm_y = int(self.y + s.FIGHTER_H * 0.72)             # 점프킥: 아래로 뻗는 발
            else:
                arm_y = int(self.y + s.FIGHTER_H * 0.35 + 12)
            if self.facing == 1:
                fist_x = int(self.x + s.FIGHTER_W + reach)
            else:
                fist_x = int(self.x - reach)
            st["fist"] = {
                "x": fist_x, "y": arm_y,
                "r": 15 if m is not s.NORMAL_MOVE else 12,
            }
        if self.blocking:
            gx = int(self.x + s.FIGHTER_W) if self.facing == 1 else int(self.x - 8)
            st["guard"] = {"x": gx, "y": by + int(bh * 0.18), "w": 8, "h": int(bh * 0.6)}
        # 관절 골격 (머리·몸통·팔·다리) — 동작에 따라 포즈가 바뀐다
        self._pose(st)
        return st

    def _pose(self, st):
        """동작별 스틱 캐릭터 골격을 계산해 st["skel"] 에 채운다.

        모든 좌표는 절대 화면 좌표. 데스크톱/웹 렌더러가 이 점들을 그대로 그린다.
        """
        bx, by, bw, bh = st["bx"], st["by"], st["bw"], st["bh"]
        fdir = self.facing
        cx = bx + bw // 2
        bottom = by + bh

        head_r = max(9, round(bh * 0.13))
        head_cy = by + head_r + 2
        sh_y = head_cy + head_r
        hip_y = by + round(bh * 0.55)
        sh_dx = round(bw * 0.15)
        hip_dx = round(bw * 0.13)

        front_sh = (cx + fdir * sh_dx, sh_y)
        back_sh = (cx - fdir * sh_dx, sh_y)
        front_hip = (cx + fdir * hip_dx, hip_y)
        back_hip = (cx - fdir * hip_dx, hip_y)

        # ---- 다리 ----
        walking = self.on_ground and abs(self.vx) > 0.6 and not self.is_attacking
        if not self.on_ground:                      # 공중: 다리 오므림
            ff = (cx + fdir * round(bw * 0.16), hip_y + round(bh * 0.22))
            bf = (cx - fdir * round(bw * 0.08), hip_y + round(bh * 0.26))
        elif walking:                               # 걷기: 발 번갈아 스윙
            ph = self.anim_t * 0.4
            ff = (cx + fdir * round(bw * 0.14 + math.sin(ph) * bw * 0.22),
                  bottom - round(max(0.0, math.sin(ph)) * bh * 0.07))
            bf = (cx - fdir * round(bw * 0.14 - math.sin(ph) * bw * 0.22),
                  bottom - round(max(0.0, -math.sin(ph)) * bh * 0.07))
        else:                                       # 대기: 벌린 스탠스
            ff = (cx + fdir * round(bw * 0.26), bottom)
            bf = (cx - fdir * round(bw * 0.20), bottom)

        def bend(a, b, out, down):
            return (int((a[0] + b[0]) / 2 + fdir * out), int((a[1] + b[1]) / 2 + down))

        leg_f = [front_hip, bend(front_hip, ff, bw * 0.10, 0), (int(ff[0]), int(ff[1]))]
        leg_b = [back_hip, bend(back_hip, bf, bw * 0.06, 0), (int(bf[0]), int(bf[1]))]

        # ---- 팔 ----
        if self.hitstun > 0:                        # 피격: 팔 뒤로 젖힘
            hand_f = (cx - fdir * round(bw * 0.04), sh_y - round(bh * 0.03))
            hand_b = (cx - fdir * round(bw * 0.22), sh_y + round(bh * 0.02))
        elif self.blocking:                         # 가드: 두 팔 앞으로 모음
            hand_f = (cx + fdir * round(bw * 0.30), sh_y + round(bh * 0.02))
            hand_b = (cx + fdir * round(bw * 0.16), sh_y + round(bh * 0.08))
        else:                                       # 대기/걷기: 기본 가드 자세
            hand_f = (cx + fdir * round(bw * 0.34), sh_y + round(bh * 0.09))
            hand_b = (cx + fdir * round(bw * 0.10), sh_y + round(bh * 0.13))

        # 공격: 펀치면 앞손이, 킥이면 앞발이 타격점(fist)까지 뻗는다
        is_kick = False
        if self.is_attacking and st["fist"]:
            tgt = (st["fist"]["x"], st["fist"]["y"])
            lvl = self.move["level"]
            if lvl in ("low", "overhead"):          # 로우킥/점프킥 = 발차기
                is_kick = True
                leg_f = [front_hip, bend(front_hip, tgt, bw * 0.05, 0),
                         (int(tgt[0]), int(tgt[1]))]
            else:                                   # 펀치/대시펀치/어퍼컷 = 주먹
                hand_f = tgt

        arm_f = [front_sh, bend(front_sh, hand_f, 0, round(bh * 0.05)),
                 (int(hand_f[0]), int(hand_f[1]))]
        arm_b = [back_sh, bend(back_sh, hand_b, 0, round(bh * 0.05)),
                 (int(hand_b[0]), int(hand_b[1]))]

        st["skel"] = {
            "head": [cx, head_cy, head_r],
            "torso": [list(back_sh), list(front_sh), list(front_hip), list(back_hip)],
            "arm_f": [list(map(int, p)) for p in arm_f],
            "arm_b": [list(map(int, p)) for p in arm_b],
            "leg_f": [list(map(int, p)) for p in leg_f],
            "leg_b": [list(map(int, p)) for p in leg_b],
            "lw": max(4, round(bw * 0.13)),
            "joint": max(3, round(bw * 0.09)),
            "kick": is_kick,
        }
        # 눈은 머리 위로 이동
        st["eye"] = (cx + fdir * round(head_r * 0.45), head_cy)

    # ---- 렌더링 (Draw) ----
    def draw(self, surface):
        st = self.render_state()
        body = pygame.Rect(st["bx"], st["by"], st["bw"], st["bh"])
        sk = st["skel"]

        # 상태 오라 (몸 뒤에 먼저 깔림)
        if st["counter"] > 0 and (st["counter"] // 3) % 2 == 0:
            pygame.draw.rect(surface, s.COUNTER_COLOR, body.inflate(16, 16), border_radius=14)
        gb = st["guard_break"]
        if gb > 0 and (gb // 4) % 2 == 0:
            color = s.GUARD_BREAK_COLOR
        else:
            color = s.WHITE if st["flash"] else self.color

        lw = sk["lw"]
        jr = sk["joint"]

        def limb(pts):
            pygame.draw.lines(surface, color, False, pts, lw)
            for p in pts:
                pygame.draw.circle(surface, color, p, lw // 2)
            pygame.draw.circle(surface, self.accent, pts[-1], jr)  # 손/발 강조

        # 뒤쪽 팔·다리 → 몸통 → 머리 → 앞쪽 다리·팔 (깊이감)
        limb(sk["arm_b"])
        limb(sk["leg_b"])
        pygame.draw.polygon(surface, color, sk["torso"])
        pygame.draw.polygon(surface, self.accent, sk["torso"], width=2)
        hx, hy, hr = sk["head"]
        pygame.draw.circle(surface, color, (hx, hy), hr)
        pygame.draw.circle(surface, self.accent, (hx, hy), hr, 2)
        limb(sk["leg_f"])
        limb(sk["arm_f"])

        # 상태 외곽선
        if st["hurt"] > 0:
            pygame.draw.rect(surface, s.SPARK_COLOR, body.inflate(6, 6), width=2, border_radius=10)
        if gb > 0:
            pygame.draw.rect(surface, s.GUARD_BREAK_COLOR, body.inflate(10, 10), width=3, border_radius=12)
        if st["counter"] > 0:
            pygame.draw.rect(surface, s.COUNTER_COLOR, body.inflate(8, 8), width=3, border_radius=11)

        # 눈
        pygame.draw.circle(surface, s.BLACK, st["eye"], max(3, hr // 3))

        # 공격 임팩트(주먹/발) 강조 원
        if st["fist"]:
            f = st["fist"]
            pygame.draw.circle(surface, s.ATTACK_COLOR, (f["x"], f["y"]), f["r"])

        # 방어 시 가드 표시
        if st["guard"]:
            g = st["guard"]
            pygame.draw.rect(surface, s.BLOCK_COLOR,
                             (g["x"], g["y"], g["w"], g["h"]), border_radius=4)
