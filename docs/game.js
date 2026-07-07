// 브라우저 클라이언트 — "얇은 렌더러".
// 게임 로직은 전부 서버(Python Match)에 있다. 여기서는
// 1) 키 입력을 서버로 보내고  2) 서버가 보낸 상태 스냅샷을 캔버스에 그린다.
// 도형 좌표(fist/guard/eye 등)까지 서버가 계산해 주므로 로직 중복이 없다.

"use strict";

// ---- 상수 (game/settings.py 와 시각 상수만 동기화) ----
const W = 960, H = 540, GROUND_Y = H - 80;
const FIGHTER_W = 60, FIGHTER_H = 110, MAX_HEALTH = 100;
const COLORS = {
  white: "rgb(240,240,240)", black: "rgb(18,18,22)", grey: "rgb(90,90,100)",
  bgTop: "rgb(40,44,70)", bgBottom: "rgb(18,20,34)", ground: "rgb(52,46,40)",
  p1: "rgb(70,150,240)", p1Accent: "rgb(150,200,255)",
  p2: "rgb(240,90,90)", p2Accent: "rgb(255,160,160)",
  healthGood: "rgb(80,210,110)", healthLow: "rgb(230,80,80)",
  attack: "rgb(255,220,120)", block: "rgb(120,220,255)",
};

// ---- 키 → 액션 매핑 (혼자 플레이하므로 WASD와 방향키 둘 다 자신에게 매핑) ----
const KEYMAP = {
  KeyA: "left", ArrowLeft: "left",
  KeyD: "right", ArrowRight: "right",
  KeyW: "jump", ArrowUp: "jump",
  KeyS: "down", ArrowDown: "down",
  KeyF: "attack", Period: "attack",
  KeyG: "block", Slash: "block",
};

// ---- DOM ----
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const overlay = document.getElementById("overlay");
const statusEl = document.getElementById("status");
const lobbyEl = document.getElementById("lobby");
const shareEl = document.getElementById("share");
const copyBtn = document.getElementById("btn-copy");

// ---- 연결 상태 ----
let ws = null;
let mySide = null;
let lastState = null;
let started = false;

const params = new URLSearchParams(location.search);
const SERVER = params.get("server") || window.GAME_SERVER;

function setStatus(text) { statusEl.textContent = text; }

function showLobby() {
  lobbyEl.style.display = "block";
  setStatus("방을 만들거나 코드로 참가하세요");
}

function shareUrl(code) {
  const url = new URL(location.href);
  url.searchParams.set("room", code);
  if (params.get("server")) url.searchParams.set("server", params.get("server"));
  return url.toString();
}

// ---- WebSocket ----
function connect(onOpen) {
  ws = new WebSocket(SERVER);
  ws.onopen = onOpen;
  ws.onclose = () => {
    if (!started) setStatus("서버에 연결할 수 없습니다. 서버 주소를 확인하세요: " + SERVER);
    else { overlay.classList.remove("hidden"); setStatus("서버와의 연결이 끊어졌습니다"); }
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.t === "room") {
      mySide = msg.side;
      if (mySide === "P1") {
        lobbyEl.style.display = "none";
        shareEl.style.display = "block";
        copyBtn.style.display = "inline-block";
        shareEl.textContent = shareUrl(msg.code);
        setStatus("방 코드: " + msg.code + " — 친구가 접속하길 기다리는 중...");
      } else {
        setStatus("참가 완료! 곧 시작합니다...");
      }
    } else if (msg.t === "start") {
      started = true;
      overlay.classList.add("hidden");
    } else if (msg.t === "state") {
      lastState = msg.s;
    } else if (msg.t === "peer_left") {
      overlay.classList.remove("hidden");
      lobbyEl.style.display = "none";
      shareEl.style.display = "none";
      copyBtn.style.display = "none";
      setStatus("상대가 나갔습니다. 새로고침해서 다시 시작하세요.");
    } else if (msg.t === "error") {
      setStatus(msg.msg);
      lobbyEl.style.display = "block";
    }
  };
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

// ---- 로비 UI ----
document.getElementById("btn-create").onclick = () => {
  lobbyEl.style.display = "none";
  setStatus("방을 만드는 중...");
  send({ t: "create" });
};
document.getElementById("btn-join").onclick = () => {
  const code = document.getElementById("room-input").value.trim().toUpperCase();
  if (code.length === 4) send({ t: "join", room: code });
};
copyBtn.onclick = () => {
  navigator.clipboard.writeText(shareEl.textContent);
  copyBtn.textContent = "복사됨!";
  setTimeout(() => (copyBtn.textContent = "링크 복사"), 1500);
};

// ---- 키 입력 ----
window.addEventListener("keydown", (e) => {
  if (e.repeat) return;                       // 커맨드 판정에 자동 반복 입력 금지
  if (e.code === "KeyR") { send({ t: "restart" }); return; }
  const action = KEYMAP[e.code];
  if (action) { e.preventDefault(); send({ t: "key", a: action, d: true }); }
});
window.addEventListener("keyup", (e) => {
  const action = KEYMAP[e.code];
  if (action) { e.preventDefault(); send({ t: "key", a: action, d: false }); }
});

// ---- 렌더링 (데스크톱 game.py draw 와 동일한 모양) ----
const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
bgGrad.addColorStop(0, COLORS.bgTop);
bgGrad.addColorStop(1, COLORS.bgBottom);

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function drawFighter(f, color, accent) {
  // 몸통
  ctx.fillStyle = f.flash ? COLORS.white : color;
  roundRect(f.x, f.y, FIGHTER_W, FIGHTER_H, 8);
  ctx.fill();
  ctx.strokeStyle = accent;
  ctx.lineWidth = 3;
  roundRect(f.x, f.y, FIGHTER_W, FIGHTER_H, 8);
  ctx.stroke();
  // 눈
  ctx.fillStyle = COLORS.black;
  ctx.beginPath();
  ctx.arc(f.eye[0], f.eye[1], 5, 0, Math.PI * 2);
  ctx.fill();
  // 주먹
  if (f.fist) {
    ctx.fillStyle = COLORS.attack;
    ctx.beginPath();
    ctx.arc(f.fist.x, f.fist.y, f.fist.r, 0, Math.PI * 2);
    ctx.fill();
  }
  // 가드
  if (f.guard) {
    ctx.fillStyle = COLORS.block;
    roundRect(f.guard.x, f.guard.y, f.guard.w, f.guard.h, 4);
    ctx.fill();
  }
}

function drawHealthBar(health, x, alignLeft) {
  const w = 360, h = 26, y = 24;
  ctx.fillStyle = COLORS.black;
  roundRect(x - 3, y - 3, w + 6, h + 6, 6); ctx.fill();
  ctx.fillStyle = COLORS.grey;
  roundRect(x, y, w, h, 4); ctx.fill();
  const ratio = health / MAX_HEALTH;
  const fillW = Math.floor(w * ratio);
  if (fillW > 0) {
    ctx.fillStyle = ratio > 0.3 ? COLORS.healthGood : COLORS.healthLow;
    roundRect(alignLeft ? x : x + w - fillW, y, fillW, h, 4);
    ctx.fill();
  }
}

function drawCenterText(title, subtitle) {
  ctx.fillStyle = "rgba(0,0,0,0.47)";
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = COLORS.white;
  ctx.textAlign = "center";
  ctx.font = "bold 56px Consolas, monospace";
  ctx.fillText(title, W / 2, H / 2 - 20);
  if (subtitle) {
    ctx.font = "bold 18px Consolas, monospace";
    ctx.fillText(subtitle, W / 2, H / 2 + 30);
  }
}

function draw() {
  requestAnimationFrame(draw);
  // 배경 + 바닥
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = COLORS.ground;
  ctx.fillRect(0, GROUND_Y, W, H - GROUND_Y);
  ctx.strokeStyle = COLORS.grey;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(0, GROUND_Y); ctx.lineTo(W, GROUND_Y);
  ctx.stroke();

  const st = lastState;
  if (!st) return;

  const [f1, f2] = st.fighters;
  drawFighter(f1, COLORS.p1, COLORS.p1Accent);
  drawFighter(f2, COLORS.p2, COLORS.p2Accent);

  // HUD
  drawHealthBar(f1.health, 30, true);
  drawHealthBar(f2.health, W - 30 - 360, false);
  ctx.fillStyle = COLORS.white;
  ctx.font = "bold 18px Consolas, monospace";
  ctx.textAlign = "left";
  ctx.fillText("P1 " + "●".repeat(st.wins.P1) + (mySide === "P1" ? "  (YOU)" : ""), 30, 74);
  ctx.textAlign = "right";
  ctx.fillText((mySide === "P2" ? "(YOU)  " : "") + "●".repeat(st.wins.P2) + " P2", W - 30, 74);
  ctx.textAlign = "center";
  ctx.font = "bold 30px Consolas, monospace";
  ctx.fillText(String(st.time), W / 2, 64);

  // 특수기 팝업
  if (st.popup) {
    ctx.fillStyle = COLORS.attack;
    ctx.font = "bold 30px Consolas, monospace";
    ctx.fillText(st.popup, W / 2, 130);
  }

  // 라운드/매치 종료 표시
  if (st.match_over) {
    drawCenterText(st.match_winner + " WINS THE MATCH!", "R 키로 재시작");
  } else if (st.round_over) {
    drawCenterText(st.round_winner === "DRAW" ? "DRAW" : st.round_winner + " WINS ROUND", null);
  }
}

// ---- 시작 ----
connect(() => {
  const roomFromUrl = params.get("room");
  if (roomFromUrl) {
    setStatus("방 " + roomFromUrl.toUpperCase() + " 에 참가하는 중...");
    send({ t: "join", room: roomFromUrl });
  } else {
    showLobby();
  }
});
draw();
