"""데스크톱 클라이언트 — 렌더링, 로컬 입력(키 → 액션 변환), 메인 루프.

시뮬레이션 로직은 전부 Match(game/match.py)에 있다. 이 파일은
pygame 키 입력을 액션으로 변환해 Match에 넣고, Match의 상태를 그린다.
"""

import asyncio
import math
import random

import pygame

from . import settings as s
from .match import Match

P1_CONTROLS = {
    "left": pygame.K_a,
    "right": pygame.K_d,
    "jump": pygame.K_w,
    "down": pygame.K_s,
    "attack": pygame.K_f,
    "block": pygame.K_g,
}

P2_CONTROLS = {
    "left": pygame.K_LEFT,
    "right": pygame.K_RIGHT,
    "jump": pygame.K_UP,
    "down": pygame.K_DOWN,
    "attack": pygame.K_PERIOD,
    "block": pygame.K_SLASH,
}


class Game:
    def __init__(self):
        pygame.display.set_caption(s.TITLE)
        self.screen = pygame.display.set_mode((s.WIDTH, s.HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.SysFont("consolas", 64, bold=True)
        self.font_mid = pygame.font.SysFont("consolas", 32, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 20, bold=True)

        self._background = self._make_background()
        self._world = pygame.Surface((s.WIDTH, s.HEIGHT))  # 흔들림 적용용 오프스크린
        self.running = True
        self.match = Match()

    # ---- 입력 변환 (Key -> action) ----
    @staticmethod
    def _actions(keys, controls):
        """pygame 눌림 상태를 액션 딕셔너리로 변환."""
        return {action: bool(keys[key]) for action, key in controls.items()}

    def _dispatch_keydown(self, key):
        """이산 KEYDOWN을 해당 플레이어의 커맨드 입력으로 전달."""
        for side, controls in (("P1", P1_CONTROLS), ("P2", P2_CONTROLS)):
            for action, k in controls.items():
                if key == k:
                    self.match.key_event(side, action)

    # ---- 렌더링 (Draw) ----
    def _make_background(self):
        """세로 그라데이션 배경 + 바닥을 미리 그려 재사용."""
        bg = pygame.Surface((s.WIDTH, s.HEIGHT))
        for y in range(s.HEIGHT):
            t = y / s.HEIGHT
            r = int(s.BG_TOP[0] + (s.BG_BOTTOM[0] - s.BG_TOP[0]) * t)
            g = int(s.BG_TOP[1] + (s.BG_BOTTOM[1] - s.BG_TOP[1]) * t)
            b = int(s.BG_TOP[2] + (s.BG_BOTTOM[2] - s.BG_TOP[2]) * t)
            pygame.draw.line(bg, (r, g, b), (0, y), (s.WIDTH, y))
        pygame.draw.rect(bg, s.GROUND_COLOR, (0, s.GROUND_Y, s.WIDTH, s.HEIGHT - s.GROUND_Y))
        pygame.draw.line(bg, s.GREY, (0, s.GROUND_Y), (s.WIDTH, s.GROUND_Y), 3)
        return bg

    def draw(self):
        m = self.match

        # 월드(배경+파이터+스파크)를 오프스크린에 그린 뒤 흔들림 오프셋으로 blit.
        # HUD/오버레이는 흔들리지 않게 화면에 직접 그린다.
        self._world.blit(self._background, (0, 0))
        m.p1.draw(self._world)
        m.p2.draw(self._world)
        self._draw_effects(self._world, m.effects)

        if m.shake > 0:
            mag = int(s.SHAKE_MAG * min(1.0, m.shake / s.SHAKE_SPECIAL))
            dx = random.randint(-mag, mag)
            dy = random.randint(-mag, mag)
            self.screen.fill(s.BLACK)
        else:
            dx = dy = 0
        self.screen.blit(self._world, (dx, dy))

        self._draw_hud()

        if m.match_over:
            self._draw_center_text(
                f"{m.match_winner} WINS THE MATCH!",
                "R 키로 재시작 (Press R to restart)",
            )
        elif m.round_over:
            if m.round_winner == "DRAW":
                self._draw_center_text("DRAW", None)
            else:
                self._draw_center_text(f"{m.round_winner} WINS ROUND", None)

        pygame.display.flip()

    def _draw_effects(self, surface, effects):
        """임팩트 스파크: 방사형 선 + 중심 원 (수명에 따라 커지며 사라짐)."""
        for e in effects:
            t = e["life"] / e["max"]        # 1.0 → 0.0 (raw effect 딕셔너리)
            grow = 1.0 - t                  # 진행도 (터질수록 확산)
            kind = e.get("kind")
            if kind == "guardbreak":
                self._draw_guard_break(surface, e["x"], e["y"], t, grow)
                continue
            if kind == "dust":
                cx, cy = e["x"], e["y"]
                for k in (-1, 0, 1):
                    px = cx + int(k * grow * 22)
                    py = cy - int(grow * 8)
                    pr = max(1, int((5 - abs(k)) * t))
                    if pr > 0:
                        pygame.draw.circle(surface, s.DUST_COLOR, (px, py), pr)
                continue
            blocked = e.get("block")
            spark_col = s.BLOCK_COLOR if blocked else s.SPARK_COLOR
            cx, cy = e["x"], e["y"]
            base = 16 if e["big"] else 11
            # 확산하는 링 + 중심의 밝은 원 (동그란 임팩트)
            ring_r = int(base * (0.5 + grow * 1.4))
            pygame.draw.circle(surface, spark_col, (cx, cy), ring_r, 4 if e["big"] else 3)
            core = int(base * (0.4 + t * 0.7))
            if core > 0:
                pygame.draw.circle(surface, s.WHITE, (cx, cy), core)
                pygame.draw.circle(surface, spark_col, (cx, cy), core, 2)

    def _draw_guard_break(self, surface, cx, cy, t, grow):
        """가드 브레이크 전용 이펙트: 확산하는 마젠타 링 + 파편."""
        ring_r = int(18 + grow * 46)
        pygame.draw.circle(surface, s.GUARD_BREAK_COLOR, (cx, cy), ring_r, 4)
        pygame.draw.circle(surface, s.WHITE, (cx, cy), max(2, ring_r - 8), 2)
        for i in range(8):
            ang = math.pi * i / 4 + grow * 0.5
            d = 14 + grow * 40
            x2 = cx + int(math.cos(ang) * d)
            y2 = cy + int(math.sin(ang) * d)
            pygame.draw.line(surface, s.GUARD_BREAK_COLOR,
                             (cx + int(math.cos(ang) * 10), cy + int(math.sin(ang) * 10)),
                             (x2, y2), 3)

    def _draw_hud(self):
        m = self.match

        # 체력바
        self._draw_health_bar(m.p1, x=30, align_left=True)
        self._draw_health_bar(m.p2, x=s.WIDTH - 30 - 360, align_left=False)

        # 가드 게이지 (체력바 아래 얇은 바)
        self._draw_guard_gauge(m.p1, x=30, align_left=True)
        self._draw_guard_gauge(m.p2, x=s.WIDTH - 30 - 360, align_left=False)

        # 이름 & 승수
        n1 = self.font_small.render(f"P1  {'●' * m.wins['P1']}", True, s.WHITE)
        n2 = self.font_small.render(f"{'●' * m.wins['P2']}  P2", True, s.WHITE)
        self.screen.blit(n1, (30, 66))
        self.screen.blit(n2, (s.WIDTH - 30 - n2.get_width(), 66))

        # 타이머
        seconds = max(0, m.round_frames // s.FPS)
        timer = self.font_mid.render(str(seconds), True, s.WHITE)
        self.screen.blit(timer, (s.WIDTH // 2 - timer.get_width() // 2, 40))

        # 특수기 명중 표시
        if m.popup:
            surf = self.font_mid.render(m.popup[0], True, s.ATTACK_COLOR)
            self.screen.blit(surf, (s.WIDTH // 2 - surf.get_width() // 2, 100))

    def _draw_health_bar(self, fighter, x, align_left):
        w, h, y = 360, 26, 24
        pygame.draw.rect(self.screen, s.BLACK, (x - 3, y - 3, w + 6, h + 6), border_radius=6)
        pygame.draw.rect(self.screen, s.GREY, (x, y, w, h), border_radius=4)
        ratio = fighter.health / s.MAX_HEALTH
        fill_w = int(w * ratio)
        color = s.HEALTH_GOOD if ratio > 0.3 else s.HEALTH_LOW
        if fill_w > 0:
            if align_left:
                pygame.draw.rect(self.screen, color, (x, y, fill_w, h), border_radius=4)
            else:
                pygame.draw.rect(self.screen, color, (x + w - fill_w, y, fill_w, h), border_radius=4)

    def _draw_guard_gauge(self, fighter, x, align_left):
        w, h, y = 360, 6, 53
        pygame.draw.rect(self.screen, s.BLACK, (x - 2, y - 2, w + 4, h + 4), border_radius=3)
        pygame.draw.rect(self.screen, s.GREY, (x, y, w, h), border_radius=2)
        ratio = max(0.0, min(1.0, fighter.guard_gauge / s.GUARD_MAX))
        fill_w = int(w * ratio)
        # 잠기면(가드 불가) 빨강, 낮으면 빨강, 평소 파랑
        color = s.GUARD_GAUGE_LOW if (fighter.guard_locked or ratio < 0.25) else s.GUARD_GAUGE_COLOR
        if fill_w > 0:
            gx = x if align_left else x + w - fill_w
            pygame.draw.rect(self.screen, color, (gx, y, fill_w, h), border_radius=2)

    def _draw_center_text(self, title, subtitle):
        overlay = pygame.Surface((s.WIDTH, s.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, (0, 0))

        t = self.font_big.render(title, True, s.WHITE)
        self.screen.blit(t, (s.WIDTH // 2 - t.get_width() // 2, s.HEIGHT // 2 - 60))
        if subtitle:
            st = self.font_small.render(subtitle, True, s.WHITE)
            self.screen.blit(st, (s.WIDTH // 2 - st.get_width() // 2, s.HEIGHT // 2 + 20))

    # ---- 메인 루프 (Main loop) ----
    async def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_r:
                        self.match.new_match()
                    else:
                        self._dispatch_keydown(event.key)

            keys = pygame.key.get_pressed()
            self.match.step(
                self._actions(keys, P1_CONTROLS),
                self._actions(keys, P2_CONTROLS),
            )
            self.draw()

            self.clock.tick(s.FPS)
            await asyncio.sleep(0)          # Pygbag(브라우저) 호환에 필수
