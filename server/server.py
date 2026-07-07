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

rooms = {}          # code -> Room


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


async def handler(ws):
    room = None
    side = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if room is None:
                # 첫 메시지는 create 또는 join 이어야 함
                t = msg.get("t")
                if t == "create":
                    code = _new_room_code()
                    room = Room(code)
                    rooms[code] = room
                    side = "P1"
                elif t == "join":
                    code = str(msg.get("room", "")).upper()
                    room = rooms.get(code)
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
    except websockets.ConnectionClosed:
        pass
    finally:
        if room is not None and side is not None:
            await room.remove(side)


async def health_check(connection, request):
    """Render 등의 HTTP 헬스체크에 응답 (WebSocket 업그레이드가 아닌 요청)."""
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return connection.respond(http.HTTPStatus.OK, "fight server OK\n")
    return None


async def main():
    port = int(os.environ.get("PORT", 8765))
    async with websockets.serve(handler, "0.0.0.0", port, process_request=health_check):
        print(f"fight server listening on :{port}")
        await asyncio.Future()            # 영원히 실행


if __name__ == "__main__":
    asyncio.run(main())
