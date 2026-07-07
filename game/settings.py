"""게임 전역 설정 및 상수 (Global settings and constants)."""

# 화면 (Screen)
WIDTH = 960
HEIGHT = 540
FPS = 60
TITLE = "2D Web Fight Game"

# 물리 (Physics)
GRAVITY = 0.8
GROUND_Y = HEIGHT - 80          # 바닥 y좌표 (fighters stand on this line)
JUMP_VELOCITY = -16
MOVE_SPEED = 5

# 파이터 규격 (Fighter dimensions)
FIGHTER_W = 60
FIGHTER_H = 110

# 전투 (Combat)
MAX_HEALTH = 100
ATTACK_DAMAGE = 10
ATTACK_RANGE = 70               # 주먹 히트박스 길이 (attack hitbox reach)
ATTACK_DURATION = 12            # 공격 애니메이션 프레임 수
ATTACK_ACTIVE_START = 4         # 히트박스 활성 시작 프레임
ATTACK_ACTIVE_END = 8           # 히트박스 활성 종료 프레임
ATTACK_COOLDOWN = 18            # 공격 후 재입력 대기 프레임
KNOCKBACK = 8
BLOCK_DAMAGE_MULT = 0.2         # 방어 시 데미지 배율 (chip damage)
HIT_STUN = 14                   # 피격 경직 프레임

# 라운드 (Round)
ROUND_TIME = 60                 # 초 (seconds)
ROUNDS_TO_WIN = 2               # 선승제 (best of 3)

# 커맨드 입력 (Command inputs) - 철권식 특수기
COMMAND_WINDOW = 35             # 커맨드 전체가 성립해야 하는 프레임 수
BUFFER_SIZE = 8                 # 입력 버퍼에 보관하는 최근 입력 개수

# 기본 공격 (Normal attack)
NORMAL_MOVE = {
    "name": "PUNCH",
    "seq": (),                  # 커맨드 없음 (공격 키만)
    "damage": ATTACK_DAMAGE,
    "range": ATTACK_RANGE,
    "duration": ATTACK_DURATION,
    "active": (ATTACK_ACTIVE_START, ATTACK_ACTIVE_END),
    "cooldown": ATTACK_COOLDOWN,
    "lunge": 0,                 # 시전 시 전진 속도
    "launch": 0,                # 명중 시 상대를 띄우는 수직 속도 (음수 = 위)
}

# 특수기 (Special moves) - seq는 공격 키 직전까지의 방향 입력 (facing 기준 상대 방향)
SPECIAL_MOVES = [
    {
        "name": "DASH PUNCH",   # →→ + 공격: 돌진 펀치
        "seq": ("forward", "forward"),
        "damage": 16,
        "range": 80,
        "duration": 16,
        "active": (5, 11),
        "cooldown": 30,
        "lunge": 10,
        "launch": 0,
    },
    {
        "name": "UPPERCUT",     # ↓→ + 공격: 어퍼컷 (상대를 띄움)
        "seq": ("down", "forward"),
        "damage": 14,
        "range": 60,
        "duration": 18,
        "active": (4, 10),
        "cooldown": 36,
        "lunge": 2,
        "launch": -13,
    },
]

# 색상 (Colors) - R, G, B
WHITE = (240, 240, 240)
BLACK = (18, 18, 22)
GREY = (90, 90, 100)
BG_TOP = (40, 44, 70)
BG_BOTTOM = (18, 20, 34)
GROUND_COLOR = (52, 46, 40)
P1_COLOR = (70, 150, 240)       # 파란색 (blue)
P1_ACCENT = (150, 200, 255)
P2_COLOR = (240, 90, 90)        # 빨간색 (red)
P2_ACCENT = (255, 160, 160)
HEALTH_GOOD = (80, 210, 110)
HEALTH_LOW = (230, 80, 80)
ATTACK_COLOR = (255, 220, 120)
BLOCK_COLOR = (120, 220, 255)

# 조작 키 (Controls) - pygame key 상수는 game.py에서 정의
# Player 1: A/D 이동, W 점프, S 아래(커맨드), F 공격, G 방어
# Player 2: ←/→ 이동, ↑ 점프, ↓ 아래(커맨드), .(period) 공격, /(slash) 방어
