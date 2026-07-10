"""온라인 대전 서버 — WebSocket 방(room) 기반, 서버 권위 시뮬레이션.

서버가 game.match.Match를 60Hz로 직접 실행한다(치트 불가, 동기화 문제 없음).
클라이언트는 키 입력만 보내고, 서버가 계산한 상태 스냅샷을 받아 그린다.

로컬 실행:  python server/server.py   (기본 포트 8765, PORT 환경변수로 변경)

프로토콜 (JSON):
  C→S {"t":"create"}                     방 생성
  C→S {"t":"join","room":"ABCD"}         방 참가
  C→S {"t":"key","a":"left","d":true}    키 눌림/뗌 (a=액션, d=down 여부)
  C→S {"t":"restart"}                    매치 종료 후 재시작
  S→C {"t":"room","code":"ABCD","side":"P1"}
  S→C {"t":"start"}                      두 명 모임 → 게임 시작
  S→C {"t":"state","s":{...}}            상태 스냅샷 (60Hz)
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

from game import settings as s
from game.match import Match, ACTIONS

ROOM_CODE_CHARS = string.ascii_uppercase
FRAME_DT = 1.0 / s.FPS

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
connection_count = 0


class Room:
    def __init__(self, code):
        self.code = code
        self.match = Match()
        self.players = {}                 # "P1"/"P2" -> websocket
        self.inputs = {
            "P1": {a: False for a in ACTIONS},
            "P2": {a: False for a in ACTIONS},
        }
        self.task = None                  # 시뮬레이션 루프 태스크
        self.closed = False

    @property
    def full(self):
        return len(self.players) >= 2

    def start_if_ready(self):
        """두 명이 모이면 시뮬레이션 루프 시작."""
        if self.full and self.task is None:
            self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        """60Hz 시뮬레이션 + 상태 브로드캐스트."""
        self._broadcast({"t": "start"})
        loop = asyncio.get_event_loop()
        next_tick = loop.time()
        while not self.closed:
            self.match.step(self.inputs["P1"], self.inputs["P2"])
            self._broadcast({"t": "state", "s": self.match.state()})
            next_tick += FRAME_DT
            delay = next_tick - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_tick = loop.time()   # 밀렸으면 리셋 (스파이럴 방지)

    def _broadcast(self, msg):
        # broadcast: 논블로킹 — 느린/끊긴 클라이언트가 시뮬레이션 루프를 막지 않음
        broadcast(self.players.values(), json.dumps(msg))

    def handle_message(self, side, msg):
        t = msg.get("t")
        if t == "key":
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


async def handler(ws):
    global connection_count
    connection_count += 1
    room = None
    side = None
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

            if room is None:
                # 첫 메시지는 create 또는 join 이어야 함
                t = msg.get("t")
                if t == "create":
                    if len(rooms) >= MAX_ROOMS:
                        await ws.send(json.dumps(
                            {"t": "error", "msg": "서버가 혼잡합니다. 잠시 후 다시 시도하세요"}))
                        continue
                    code = _new_room_code()
                    room = Room(code)
                    rooms[code] = room
                    side = "P1"
                elif t == "join":
                    code = str(msg.get("room", "")).upper()
                    room = rooms.get(code) if _valid_room_code(code) else None
                    if room is None or room.full or room.closed:
                        await ws.send(json.dumps(
                            {"t": "error", "msg": "방을 찾을 수 없거나 가득 찼습니다"}))
                        room = None
                        continue
                    side = "P2"
                else:
                    continue
                room.players[side] = ws
                await ws.send(json.dumps({"t": "room", "code": room.code, "side": side}))
                room.start_if_ready()
            else:
                room.handle_message(side, msg)
    except Exception:
        # 한 연결의 어떤 오류(연결 끊김·과대 메시지·프로토콜 위반 등)도
        # 서버 전체나 다른 방에 영향을 주지 않도록 여기서 격리한다.
        pass
    finally:
        connection_count -= 1
        if room is not None and side is not None:
            await room.remove(side)


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
        await asyncio.Future()            # 영원히 실행


if __name__ == "__main__":
    asyncio.run(main())
