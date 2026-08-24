"""온라인 대전 서버 — WebSocket 방(room) 기반, 서버 권위 시뮬레이션.

서버가 game.match.Match를 60Hz로 직접 실행한다(치트 불가, 동기화 문제 없음).
클라이언트는 키 입력만 보내고, 서버가 계산한 상태 스냅샷을 받아 그린다.

로컬 실행:  python server/server.py   (기본 포트 8765, PORT 환경변수로 변경)

프로토콜 (JSON):
  C→S {"t":"create"}                     방 생성
  C→S {"t":"join","room":"ABCD"}         방 참가
  C→S {"t":"queue","id":"uuid","name":"닉"}  레이팅 대전 대기열 참가
  C→S {"t":"cancel"}                     대기열 이탈
  C→S {"t":"key","a":"left","d":true}    키 눌림/뗌 (a=액션, d=down 여부)
  C→S {"t":"restart"}                    매치 종료 후 재시작
  S→C {"t":"room","code":"ABCD","side":"P1"}
  S→C {"t":"queued","rating":1000,"waiting":2}
  S→C {"t":"matched","side":"P1","me":{...},"opp":{...}}
  S→C {"t":"start"}                      두 명 모임 → 게임 시작
  S→C {"t":"state","s":{...}}            상태 스냅샷 (60Hz)
  S→C {"t":"rating","old":1000,"new":1016,"delta":16}  매치 종료 후 레이팅 변동
  S→C {"t":"peer_left"} / {"t":"error","msg":"..."}
"""

import asyncio
import http
import json
import os
import secrets
import string
import sys

# 프로젝트 루트를 import 경로에 추가 (server/ 하위에서 실행해도 동작)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets
from websockets.asyncio.server import broadcast

import rating

from game import settings as s
from game.match import Match, ACTIONS

ROOM_CODE_CHARS = string.ascii_uppercase
FRAME_DT = 1.0 / s.FPS

# 레이팅 매칭 — 비슷한 점수끼리 붙이되, 오래 기다릴수록 허용 범위를 넓힌다.
MATCH_RANGE = 100        # 초기 허용 레이팅 차
MATCH_WIDEN = 50         # WIDEN_EVERY 초마다 넓히는 폭
MATCH_WIDEN_EVERY = 5.0
MAX_NAME_LEN = 12

# 보안·자원 제한 (Security / resource limits) — 환경변수로 조정 가능.
# 인터넷에 노출되는 서버이므로 DoS(방·연결·메시지 폭주)와 남용을 막는다.
MAX_ROOMS = int(os.environ.get("MAX_ROOMS", "500"))          # 동시 방 상한
MAX_CONNECTIONS = int(os.environ.get("MAX_CONNECTIONS", "400"))  # 동시 연결 상한
MSG_RATE = float(os.environ.get("MSG_RATE", "120"))          # 연결당 초당 메시지 상한
MAX_MSG_BYTES = 2048                                          # 수신 메시지 최대 크기
# 허용 Origin(쉼표 구분). 미설정 시 모든 origin 허용(로컬 개발·테스트 호환).
# 프로덕션에선 GitHub Pages 주소로 설정 권장: ALLOWED_ORIGINS=https://<id>.github.io
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

rooms = {}          # code -> Room
queue = []          # 레이팅 대전 대기열 (Conn 목록)
connection_count = 0


class Conn:
    """연결 하나의 상태. 대기열/방 배정이 핸들러 밖(매칭 태스크)에서도 바뀌므로 객체로 묶는다."""

    __slots__ = ("ws", "room", "side", "pid", "name", "rating", "queued_at")

    def __init__(self, ws):
        self.ws = ws
        self.room = None
        self.side = None
        self.pid = None
        self.name = ""
        self.rating = rating.START
        self.queued_at = 0.0


class Room:
    def __init__(self, code, p1_character=s.DEFAULT_CHARACTER, stage="NIGHT"):
        self.code = code
        self.p1_character = p1_character if p1_character in s.CHARACTER_PROFILES else s.DEFAULT_CHARACTER
        self.p2_character = s.DEFAULT_CHARACTER
        self.stage = stage if stage in s.STAGES else s.STAGES[0]
        self.match = Match(self.p1_character, self.p2_character, self.stage)
        self.players = {}                 # "P1"/"P2" -> websocket
        self.conns = {}                   # "P1"/"P2" -> Conn (레이팅 대전일 때만 채움)
        self.ranked = False
        self.rated = False                # 이번 매치 결과를 이미 반영했는지
        self.inputs = {
            "P1": {a: False for a in ACTIONS},
            "P2": {a: False for a in ACTIONS},
        }
        self.task = None                  # 시뮬레이션 루프 태스크
        self.closed = False
        self.ready = {"P1": False, "P2": False}
        self.rematch = {"P1": False, "P2": False}
        self.started = False

    @property
    def full(self):
        return len(self.players) >= 2

    def start_if_ready(self):
        """두 명이 모이면 시뮬레이션 루프 시작."""
        if self.full and self.task is None:
            self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        """로비 대기, 카운트다운, 60Hz 시뮬레이션 + 상태 브로드캐스트."""
        loop = asyncio.get_event_loop()
        next_tick = loop.time()
        while not self.closed:
            if not self.started:
                if self.full and all(self.ready.values()):
                    for count in (3, 2, 1):
                        if self.closed or not self.full or not all(self.ready.values()):
                            break
                        self._broadcast({"t": "countdown", "n": count})
                        await asyncio.sleep(1)
                    if self.closed or not self.full or not all(self.ready.values()):
                        continue
                    self.started = True
                    self._broadcast({"t": "start"})
                    next_tick = loop.time()
                else:
                    await asyncio.sleep(0.05)
                    continue
            self.match.step(self.inputs["P1"], self.inputs["P2"])
            self._broadcast({"t": "state", "s": self.match.state()})
            if self.ranked and self.match.match_over and not self.rated:
                self._apply_rating()
            if self.match.match_over:
                self.started = False
                self.ready = {"P1": False, "P2": False}
                self._broadcast({"t": "match_finished"})
            next_tick += FRAME_DT
            delay = next_tick - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_tick = loop.time()   # 밀렸으면 리셋 (스파이럴 방지)

    def _broadcast(self, msg):
        # broadcast: 논블로킹 — 느린/끊긴 클라이언트가 시뮬레이션 루프를 막지 않음
        broadcast(self.players.values(), json.dumps(msg))

    def _send(self, side, msg):
        ws = self.players.get(side)
        if ws is not None:
            broadcast([ws], json.dumps(msg))       # 단건도 논블로킹 전송

    def _apply_rating(self):
        """매치 종료 시 Elo 반영 — 매치당 한 번."""
        self.rated = True
        p1, p2 = self.conns["P1"], self.conns["P2"]
        score_p1 = 1.0 if self.match.match_winner == "P1" else 0.0
        old1, new1, old2, new2 = rating.record(p1.pid, p2.pid, score_p1)
        p1.rating, p2.rating = new1, new2
        self._send("P1", {"t": "rating", "old": old1, "new": new1, "delta": new1 - old1})
        self._send("P2", {"t": "rating", "old": old2, "new": new2, "delta": new2 - old2})

    def _lobby(self):
        return {"t": "lobby", "players": len(self.players), "ready": dict(self.ready),
                "rematch": dict(self.rematch), "stage": self.stage}

    def handle_message(self, side, msg):
        t = msg.get("t")
        if t == "ready":
            if self.full and not self.started:
                self.ready[side] = bool(msg.get("ready", True))
                self._broadcast(self._lobby())
        elif t == "rematch":
            if self.match.match_over:
                self.rematch[side] = True
                self._broadcast({"t": "rematch", "ready": dict(self.rematch)})
                if all(self.rematch.values()):
                    self.match = Match(self.p1_character, self.p2_character, self.stage)
                    self.inputs = {"P1": {a: False for a in ACTIONS},
                                   "P2": {a: False for a in ACTIONS}}
                    self.rated = False
                    self.rematch = {"P1": False, "P2": False}
                    self.ready = {"P1": True, "P2": True}
                    self._broadcast(self._lobby())
        elif t == "key":
            action = msg.get("a")
            down = bool(msg.get("d"))
            if action in ACTIONS:
                self.inputs[side][action] = down
                if down:
                    # 이산 입력: 커맨드 버퍼/공격 발동
                    self.match.key_event(side, action)
        elif t == "restart":
            if self.match.match_over:
                self.match.new_match()
                self.rated = False        # 재대결도 한 판으로 쳐서 레이팅 반영
                self.ready = {"P1": True, "P2": True}

    async def remove(self, side):
        """플레이어 퇴장 처리 — 남은 쪽에 알리고 방 폐쇄."""
        self.players.pop(side, None)
        self.closed = True
        if self.task:
            self.task.cancel()
        self._broadcast({"t": "peer_left"})
        rooms.pop(self.code, None)


def _new_room_code():
    while True:
        code = "".join(secrets.choice(ROOM_CODE_CHARS) for _ in range(4))
        if code not in rooms:
            return code


def _valid_room_code(code):
    return len(code) == 4 and code.isalpha() and code.isupper()


def _clean_name(raw):
    name = "".join(c for c in str(raw or "") if c.isprintable()).strip()
    return name[:MAX_NAME_LEN] or "익명"


def _notify_queue():
    """대기 인원 변화를 대기자 모두에게 알린다."""
    for c in queue:
        broadcast([c.ws], json.dumps(
            {"t": "queued", "rating": c.rating, "waiting": len(queue)}))


def _leave_queue(conn):
    if conn in queue:
        queue.remove(conn)
        return True
    return False


def _tolerance(conn, now):
    """대기 시간이 길수록 허용 레이팅 차를 넓힌다."""
    waited = max(0.0, now - conn.queued_at)
    return MATCH_RANGE + MATCH_WIDEN * int(waited / MATCH_WIDEN_EVERY)


def _pair_waiting(now):
    """레이팅 순으로 정렬해 인접한 둘씩 조건이 맞으면 매칭."""
    global queue
    if len(rooms) >= MAX_ROOMS:
        return
    waiting = sorted(queue, key=lambda c: c.rating)
    taken = set()
    pairs = []
    for a, b in zip(waiting, waiting[1:]):
        if id(a) in taken or id(b) in taken:
            continue
        if abs(a.rating - b.rating) <= max(_tolerance(a, now), _tolerance(b, now)):
            taken.update((id(a), id(b)))
            pairs.append((a, b))
    if not pairs:
        return
    queue = [c for c in queue if id(c) not in taken]
    for a, b in pairs:
        _start_ranked(a, b)
    _notify_queue()


def _start_ranked(a, b):
    """매칭된 두 명으로 방을 만들고 바로 시작."""
    code = _new_room_code()
    room = Room(code)
    room.ranked = True
    rooms[code] = room
    for side, conn in (("P1", a), ("P2", b)):
        conn.room = room
        conn.side = side
        room.players[side] = conn.ws
        room.conns[side] = conn
    room.ready = {"P1": True, "P2": True}
    for me, opp in ((a, b), (b, a)):
        broadcast([me.ws], json.dumps({
            "t": "matched", "side": me.side,
            "me": {"name": me.name, "rating": me.rating},
            "opp": {"name": opp.name, "rating": opp.rating},
        }))
    room.start_if_ready()


async def matchmaker():
    """1초마다 대기열을 훑어 짝을 맞춘다."""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(1)
        try:
            _pair_waiting(loop.time())
        except Exception:
            pass          # 매칭 실패가 서버 전체를 멈추지 않게 격리


async def handler(ws):
    global connection_count
    connection_count += 1
    conn = Conn(ws)
    # 연결당 메시지 레이트 리미터 (토큰 버킷) — 플러딩 방지
    loop = asyncio.get_event_loop()
    tokens = MSG_RATE
    last = loop.time()
    strikes = 0                               # 연속 초과 횟수 (지속 폭주 시 연결 종료)
    try:
        async for raw in ws:
            # 레이트 제한: 파싱 전에 검사해 폭주 시 처리 비용 자체를 차단
            now = loop.time()
            tokens = min(MSG_RATE, tokens + (now - last) * MSG_RATE)
            last = now
            if tokens < 1:
                strikes += 1
                if strikes > MSG_RATE:        # 지속적인 폭주 → 연결 끊어 부하 차단
                    break
                continue                      # 일시 초과분은 조용히 버림
            strikes = 0
            tokens -= 1

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(msg, dict):     # 배열/숫자 등 비정상 페이로드 차단
                continue

            if conn.room is None:
                # 방 배정 전: create / join / queue / cancel 만 처리
                t = msg.get("t")
                if t == "queue":
                    if conn in queue:
                        continue
                    conn.pid = str(msg.get("id", ""))[:64]
                    if not conn.pid:
                        continue
                    conn.name = _clean_name(msg.get("name"))
                    conn.rating = rating.get(conn.pid, conn.name)["r"]
                    conn.queued_at = loop.time()
                    queue.append(conn)
                    _notify_queue()
                    continue
                if t == "cancel":
                    _leave_queue(conn)
                    _notify_queue()
                    continue
                if t == "create":
                    if len(rooms) >= MAX_ROOMS:
                        await ws.send(json.dumps(
                            {"t": "error", "msg": "서버가 혼잡합니다. 잠시 후 다시 시도하세요"}))
                        continue
                    code = _new_room_code()
                    conn.room = Room(
                        code,
                        str(msg.get("character", s.DEFAULT_CHARACTER)).upper(),
                        str(msg.get("stage", "NIGHT")).upper(),
                    )
                    rooms[code] = conn.room
                    conn.side = "P1"
                elif t == "join":
                    code = str(msg.get("room", "")).upper()
                    found = rooms.get(code) if _valid_room_code(code) else None
                    if found is None or found.full or found.closed:
                        await ws.send(json.dumps(
                            {"t": "error", "msg": "방을 찾을 수 없거나 가득 찼습니다"}))
                        continue
                    conn.room = found
                    conn.side = "P2"
                    conn.room.p2_character = str(msg.get("character", s.DEFAULT_CHARACTER)).upper()
                    if conn.room.p2_character not in s.CHARACTER_PROFILES:
                        conn.room.p2_character = s.DEFAULT_CHARACTER
                    conn.room.match = Match(conn.room.p1_character, conn.room.p2_character, conn.room.stage)
                else:
                    continue
                _leave_queue(conn)          # 대기 중이었다면 빠져나옴
                conn.room.players[conn.side] = ws
                await ws.send(json.dumps({
                    "t": "room", "code": conn.room.code, "side": conn.side,
                    "character": conn.room.p1_character if conn.side == "P1" else conn.room.p2_character,
                    "stage": conn.room.stage,
                }))
                conn.room._broadcast(conn.room._lobby())
                conn.room.start_if_ready()
            else:
                conn.room.handle_message(conn.side, msg)
    except Exception:
        # 한 연결의 어떤 오류(연결 끊김·과대 메시지·프로토콜 위반 등)도
        # 서버 전체나 다른 방에 영향을 주지 않도록 여기서 격리한다.
        pass
    finally:
        connection_count -= 1
        if _leave_queue(conn):
            _notify_queue()
        if conn.room is not None and conn.side is not None:
            await conn.room.remove(conn.side)


async def process_request(connection, request):
    """WebSocket 업그레이드 전 게이트: 헬스체크 응답 + Origin/연결수 검사."""
    # 비 웹소켓 요청(헬스체크 등)에는 200 OK
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return connection.respond(http.HTTPStatus.OK, "fight server OK\n")

    # Origin 허용목록 검사 (설정된 경우만) — 타 사이트의 남용(CSWSH) 차단
    if ALLOWED_ORIGINS:
        origin = request.headers.get("Origin")
        if origin not in ALLOWED_ORIGINS:
            return connection.respond(http.HTTPStatus.FORBIDDEN, "forbidden origin\n")

    # 동시 연결 수 상한 — 연결 폭주 DoS 방지
    if connection_count >= MAX_CONNECTIONS:
        return connection.respond(http.HTTPStatus.SERVICE_UNAVAILABLE, "server full\n")

    return None


async def main():
    port = int(os.environ.get("PORT", 8765))
    async with websockets.serve(
        handler, "0.0.0.0", port,
        process_request=process_request,
        max_size=MAX_MSG_BYTES,           # 과대 메시지 거부 (기본 1MB → 축소)
        max_queue=32,                     # 수신 큐 상한 (백프레셔)
    ):
        print(f"fight server listening on :{port}")
        asyncio.create_task(matchmaker())
        await asyncio.Future()            # 영원히 실행


if __name__ == "__main__":
    asyncio.run(main())
