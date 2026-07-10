"""게임 전역 설정 및 상수 (Global settings and constants)."""

# 화면 (Screen)
WIDTH = 960
HEIGHT = 540
FPS = 60
TITLE = "민철권"

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

# 대시 (Dash) - 같은 방향 2연타 (앞앞 = 전진, 뒤뒤 = 후진)
DASH_SPEED = 13                 # 대시 중 이동 속도
DASH_DURATION = 10             # 대시 지속 프레임

# 기본 공격 (Normal attack)
# 공격 레벨 (Attack levels) - 막기 이지선다의 핵심
#   mid      : 서서 막기로만 막힘 (앉아 막기 관통) — 앉은 상대도 맞음
#   low      : 앉아 막기로만 막힘 (서서 막기 관통)
#   overhead : 서서 막기로만 막힘 (앉아 막기 관통) — 점프 공격
# → 공격자는 low ↔ mid/overhead 를 섞고, 방어자는 서서/앉아 막기를 골라야 한다.

NORMAL_MOVE = {
    "name": "PUNCH",
    "seq": (),                  # 커맨드 없음 (공격 키만)
    "level": "mid",
    "damage": ATTACK_DAMAGE,
    "range": ATTACK_RANGE,
    "duration": ATTACK_DURATION,
    "active": (ATTACK_ACTIVE_START, ATTACK_ACTIVE_END),
    "cooldown": ATTACK_COOLDOWN,
    "lunge": 0,                 # 시전 시 전진 속도
    "launch": 0,                # 명중 시 상대를 띄우는 수직 속도 (음수 = 위)
    "stun": HIT_STUN,           # 명중 시 피격자 경직 프레임
}

# 앉아 공격 (아래 홀드 + 공격): 로우킥 — 앉아 막아야 막힌다
CROUCH_MOVE = {
    "name": "LOW KICK",
    "seq": (),
    "level": "low",
    "damage": 8,
    "range": 74,
    "duration": 14,
    "active": (4, 9),
    "cooldown": 20,
    "lunge": 0,
    "launch": 0,
    "stun": HIT_STUN,
}

# 점프 공격 (공중 + 공격): 점프킥 — 오버헤드, 서서 막아야 막힌다
AIR_MOVE = {
    "name": "JUMP KICK",
    "seq": (),
    "level": "overhead",
    "damage": 12,
    "range": 66,
    "duration": 20,
    "active": (3, 14),          # 공중 지속이 길다
    "cooldown": 6,
    "lunge": 0,
    "launch": 0,
    "stun": HIT_STUN,
}

# 특수기 (Special moves) - seq는 공격 키 직전까지의 방향 입력 (facing 기준 상대 방향)
SPECIAL_MOVES = [
    {
        "name": "UPPERCUT",     # ↓→ + 공격: 어퍼컷 (상대를 띄움 + 0.5초 스턴, 가드 시 가드브레이크)
        "seq": ("down", "forward"),
        "level": "mid",
        "damage": 14,
        "range": 60,
        "duration": 18,
        "active": (4, 10),
        "cooldown": 36,
        "lunge": 2,
        "launch": -13,
        "stun": 30,             # 0.5초 (30프레임 @ 60fps)
        "guard_break": True,    # 가드 중 맞으면 가드 붕괴 + 1초 스턴
    },
]

# 웅크리기 (Crouch)
CROUCH_H = 74                   # 앉았을 때 몸통 높이 (기본 FIGHTER_H)

# 가드 게이지 & 가드 브레이크 (Guard gauge & break)
GUARD_MAX = 120                 # 가드 게이지 최대치
GUARD_DRAIN = 1.5               # 가드 홀드 중 프레임당 소모 (약 1.3초 지속)
GUARD_REGEN = 0.7               # 가드 안 할 때 프레임당 회복
GUARD_RECOVER = 40              # 게이지 소진(락) 후 이만큼 회복돼야 다시 가드 가능
GUARD_RELEASE_CD = 12           # 가드 해제 후 재가드까지 쿨타임 (연타 방지)
GUARD_CHIP = 7                  # 공격을 막을 때 깎이는 가드 게이지 (압박)
GUARD_BREAK_STUN = 60           # 가드 브레이크 당한 유저 스턴 (1초 @ 60fps)

# 반격기 (Counter / parry) - 방어(G) 홀드 중 공격(F)
COUNTER_WINDOW = 30             # 반격 자세 유지·판정 프레임 (0.5초 @ 60fps)
COUNTER_COOLDOWN = 75           # 창 종료 후 재사용까지 추가 대기 (쿨타임)
COUNTER_MULT = 1.5             # 되돌려주는 데미지 배율
COUNTER_STUN = 24               # 반격당한 공격자 경직 프레임
COUNTER_FAIL_STUN = 36          # 반격 실패(창 만료·헛방) 시 자신이 받는 경직 (0.6초)

# 히트 이펙트 (Hit feedback)
SHAKE_NORMAL = 7                # 일반 히트 화면 흔들림 프레임
SHAKE_SPECIAL = 14             # 특수기 히트 화면 흔들림 프레임
SHAKE_MAG = 9                  # 최대 흔들림 픽셀
SPARK_LIFE = 12               # 임팩트 스파크 지속 프레임
SPARK_LIFE_BIG = 18

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
SPARK_COLOR = (255, 240, 190)   # 임팩트 스파크
HURT_RAY_COLOR = (255, 235, 150)  # 피격자에게 내리쬐는 광선
COUNTER_COLOR = (255, 220, 70)  # 반격 자세 빛남 (금색)
GUARD_GAUGE_COLOR = (120, 220, 255)  # 가드 게이지 (파랑)
GUARD_GAUGE_LOW = (255, 120, 90)     # 가드 게이지 부족/락 (빨강)
GUARD_BREAK_COLOR = (255, 80, 170)   # 가드 브레이크 이펙트 (마젠타)

# 조작 키 (Controls) - pygame key 상수는 game.py에서 정의
# Player 1: A/D 이동, W 점프, S 아래(커맨드), F 공격, G 방어
# Player 2: ←/→ 이동, ↑ 점프, ↓ 아래(커맨드), .(period) 공격, /(slash) 방어
