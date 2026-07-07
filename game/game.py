"""데스크톱 클라이언트 — 렌더링, 로컬 입력(키 → 액션 변환), 메인 루프.

시뮬레이션 로직은 전부 Match(game/match.py)에 있다. 이 파일은
pygame 키 입력을 액션으로 변환해 Match에 넣고, Match의 상태를 그린다.
"""

import asyncio

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
        self.screen.blit(self._background, (0, 0))

        m.p1.draw(self.screen)
        m.p2.draw(self.screen)

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

    def _draw_hud(self):
        m = self.match

        # 체력바
        self._draw_health_bar(m.p1, x=30, align_left=True)
        self._draw_health_bar(m.p2, x=s.WIDTH - 30 - 360, align_left=False)

        # 이름 & 승수
        n1 = self.font_small.render(f"P1  {'●' * m.wins['P1']}", True, s.WHITE)
        n2 = self.font_small.render(f"{'●' * m.wins['P2']}  P2", True, s.WHITE)
        self.screen.blit(n1, (30, 58))
        self.screen.blit(n2, (s.WIDTH - 30 - n2.get_width(), 58))

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
