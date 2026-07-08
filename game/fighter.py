"""파이터(캐릭터) 클래스 — 상태머신, 물리, 전투 로직.

입력은 pygame 키가 아니라 액션 이름("left"/"right"/"jump"/"down"/"attack"/"block")으로
받는다. 키 → 액션 변환은 로컬 클라이언트(game.py)나 서버가 담당하므로,
이 클래스는 데스크톱/서버 어디서든 동일하게 동작한다.
"""

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
        self.has_hit = False              # 이번 공격이 이미 명중했는지 (다단히트 방지)
        self.move = s.NORMAL_MOVE         # 현재/마지막 시전한 기술
        self.input_buffer = []            # [(frame, token)] - 커맨드 판정용 최근 방향 입력

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

    # ---- 입력 (Input) ----
    def handle_input(self, actions):
        """눌림 상태 액션 딕셔너리로 이동/점프/방어/웅크리기를 처리한다 (연속 입력)."""
        self.holding_down = actions["down"]

        # 경직 중이거나 KO면 입력 무시
        if self.hitstun > 0 or self.is_ko:
            self.blocking = False
            self.crouching = False
            return

        moving = False

        # 웅크리기: 지상에서 아래 홀드 (공격 중이 아닐 때). 걷기/점프 불가.
        self.crouching = actions["down"] and self.on_ground and not self.is_attacking

        # 방어: 방어 중에는 이동 불가. 아래+방어 = 앉아 막기(crouching과 공존).
        self.blocking = actions["block"] and self.on_ground

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

    def _try_attack(self, frame):
        """상황(공중/앉기/커맨드)에 맞는 기술을 골라 시전한다.

        우선순위:
          1) 공중       → 점프킥 (오버헤드)
          2) 커맨드 매치 → 특수기 (어퍼컷 등, 아래를 눌러도 커맨드가 우선)
          3) 아래 홀드   → 로우킥
          4) 그 외       → 기본 펀치
        """
        if self.hitstun > 0 or self.is_ko or self.is_attacking or self.cooldown > 0:
            return
        # 지상에서 방어 중엔 공격 불가 (공중엔 방어 개념이 없으므로 점프킥 허용)
        if self.blocking and self.on_ground:
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

    def _buffer_ends_with(self, seq, frame):
        """최근 COMMAND_WINDOW 프레임 내 방향 입력이 seq로 끝나는지 검사."""
        recent = [t for f, t in self.input_buffer if frame - f <= s.COMMAND_WINDOW]
        return tuple(recent[-len(seq):]) == tuple(seq)

    # ---- 상태 갱신 (Update) ----
    def update(self):
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
        if self.cooldown > 0:
            self.cooldown -= 1
        if self.hitstun > 0:
            self.hitstun -= 1
            # 경직 중 넉백 감쇠
            self.x += self.vx
            self.x = max(0.0, min(self.x, s.WIDTH - s.FIGHTER_W))
            self.vx *= 0.8

    def face(self, opponent):
        """항상 상대를 바라보도록 방향 갱신 (공중/공격 중에는 고정)."""
        if self.on_ground and not self.is_attacking and self.hitstun == 0:
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
            # 점프킥: 몸통 위쪽 (내려찍기)
            h = 34
            y = int(self.y + s.FIGHTER_H * 0.15)
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
                arm_y = int(self.y + s.FIGHTER_H * 0.18)              # 점프킥 위쪽
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
        return st

    # ---- 렌더링 (Draw) ----
    def draw(self, surface):
        st = self.render_state()
        body = pygame.Rect(st["bx"], st["by"], st["bw"], st["bh"])

        # 피격 시 위에서 내리쬐는 광선 (몸통보다 먼저 그려 뒤에 깔리게)
        if st["hurt"] > 0:
            self._draw_hurt_rays(surface, st["hurt"])

        color = s.WHITE if st["flash"] else self.color
        pygame.draw.rect(surface, color, body, border_radius=8)
        pygame.draw.rect(surface, self.accent, body, width=3, border_radius=8)

        # 피격 중 밝은 외곽 글로우
        if st["hurt"] > 0:
            pygame.draw.rect(surface, s.SPARK_COLOR, body.inflate(6, 6),
                             width=3, border_radius=10)

        # 눈 (바라보는 방향 표시)
        pygame.draw.circle(surface, s.BLACK, st["eye"], 5)

        # 공격 시 주먹
        if st["fist"]:
            f = st["fist"]
            pygame.draw.circle(surface, s.ATTACK_COLOR, (f["x"], f["y"]), f["r"])

        # 방어 시 가드 표시
        if st["guard"]:
            g = st["guard"]
            pygame.draw.rect(surface, s.BLOCK_COLOR,
                             (g["x"], g["y"], g["w"], g["h"]), border_radius=4)

    def _draw_hurt_rays(self, surface, hurt):
        """피격자 위에서 아래로 내리쬐는 반투명 광선 3줄 (경직 동안 반짝임)."""
        alpha = int(150 * min(1.0, hurt / s.HIT_STUN))
        ray = pygame.Surface((s.WIDTH, s.HEIGHT), pygame.SRCALPHA)
        cx = int(self.center_x)
        top = max(0, int(self.y) - 120)
        for off in (-18, 0, 18):
            # 위는 좁고 아래로 퍼지는 광선 (스포트라이트 느낌)
            pts = [
                (cx + off - 3, top),
                (cx + off + 3, top),
                (cx + off + 12, int(self.y) + 20),
                (cx + off - 12, int(self.y) + 20),
            ]
            pygame.draw.polygon(ray, (*s.HURT_RAY_COLOR, alpha), pts)
        surface.blit(ray, (0, 0))
