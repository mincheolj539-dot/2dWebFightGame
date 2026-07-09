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
  spark: "rgb(255,240,190)", hurtRay: "255,235,150",
  counter: "rgb(255,220,70)",
};
const HIT_STUN = 14, SHAKE_MAG = 9, SHAKE_SPECIAL = 14;  // settings.py와 동기화

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
  ws.onopen = () => { flushPending(); onOpen(); };
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

// 소켓이 아직 열리지 않았으면(Render 콜드 스타트 등) 보류했다가 open 시 전송.
let pendingSend = null;
function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  else pendingSend = obj;              // 방 생성/참가 클릭이 연결 전에 눌린 경우
}
function flushPending() {
  if (pendingSend && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(pendingSend));
    pendingSend = null;
  }
}

// ---- 로비 UI ----
// 아직 연결 전이면 "서버 깨우는 중" 안내 (Render 무료 서버 콜드 스타트는 최대 1분).
const connecting = () => !(ws && ws.readyState === WebSocket.OPEN);
document.getElementById("btn-create").onclick = () => {
  lobbyEl.style.display = "none";
  setStatus(connecting() ? "서버 깨우는 중... (무료 서버라 최대 1분 걸릴 수 있어요)"
                         : "방을 만드는 중...");
  send({ t: "create" });              // 연결 전이면 큐에 담겨 열릴 때 자동 전송
};
document.getElementById("btn-join").onclick = () => {
  const code = document.getElementById("room-input").value.trim().toUpperCase();
  if (code.length !== 4) return;
  setStatus(connecting() ? "서버 깨우는 중... (무료 서버라 최대 1분 걸릴 수 있어요)"
                         : "방 " + code + " 에 참가하는 중...");
  send({ t: "join", room: code });
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

function drawHurtRays(f) {
  // 피격자 위에서 아래로 내리쬐는 반투명 광선 3줄
  const alpha = 0.6 * Math.min(1, f.hurt / HIT_STUN);
  const cx = f.x + FIGHTER_W / 2;
  const top = Math.max(0, f.y - 120);
  ctx.fillStyle = "rgba(" + COLORS.hurtRay + "," + alpha + ")";
  for (const off of [-18, 0, 18]) {
    ctx.beginPath();
    ctx.moveTo(cx + off - 3, top);
    ctx.lineTo(cx + off + 3, top);
    ctx.lineTo(cx + off + 12, f.y + 20);
    ctx.lineTo(cx + off - 12, f.y + 20);
    ctx.closePath();
    ctx.fill();
  }
}

function drawFighter(f, color, accent) {
  // 몸통 박스 (웅크리면 높이가 줄고 발은 바닥에 유지) — 서버가 계산한 bx/by/bw/bh 사용
  const bx = f.bx, by = f.by, bw = f.bw, bh = f.bh;
  // 피격 시 내리쬐는 광선 (몸통보다 먼저 그려 뒤에 깔리게)
  if (f.hurt > 0) drawHurtRays(f);
  // 반격 자세: 몸통 뒤에 금색 오라 (깜빡임)
  if (f.counter > 0 && Math.floor(f.counter / 3) % 2 === 0) {
    ctx.fillStyle = COLORS.counter;
    roundRect(bx - 8, by - 8, bw + 16, bh + 16, 12);
    ctx.fill();
  }
  // 몸통
  ctx.fillStyle = f.flash ? COLORS.white : color;
  roundRect(bx, by, bw, bh, 8);
  ctx.fill();
  ctx.strokeStyle = accent;
  ctx.lineWidth = 3;
  roundRect(bx, by, bw, bh, 8);
  ctx.stroke();
  // 피격 중 밝은 외곽 글로우
  if (f.hurt > 0) {
    ctx.strokeStyle = COLORS.spark;
    ctx.lineWidth = 3;
    roundRect(bx - 3, by - 3, bw + 6, bh + 6, 10);
    ctx.stroke();
  }
  // 반격 자세 금색 외곽선
  if (f.counter > 0) {
    ctx.strokeStyle = COLORS.counter;
    ctx.lineWidth = 3;
    roundRect(bx - 4, by - 4, bw + 8, bh + 8, 11);
    ctx.stroke();
  }
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

function drawWorld() {
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
}

function drawEffects(effects) {
  // 임팩트 스파크: 방사형 선 + 중심 원 (수명에 따라 커지며 사라짐)
  for (const e of effects) {
    const grow = 1 - e.t;
    const sparkCol = e.block ? COLORS.block : COLORS.spark;  // 가드 시 파란 스파크
    const n = e.big ? 10 : 7;
    const base = e.big ? 34 : 22;
    const length = base * (0.4 + grow);
    const inner = base * 0.3 * (0.4 + grow);
    ctx.strokeStyle = sparkCol;
    ctx.lineWidth = e.big ? 4 : 3;
    for (let i = 0; i < n; i++) {
      const ang = (2 * Math.PI * i / n) + grow;
      ctx.beginPath();
      ctx.moveTo(e.x + Math.cos(ang) * inner, e.y + Math.sin(ang) * inner);
      ctx.lineTo(e.x + Math.cos(ang) * length, e.y + Math.sin(ang) * length);
      ctx.stroke();
    }
    const r = (e.big ? 10 : 7) * (0.5 + e.t);
    ctx.fillStyle = COLORS.white;
    ctx.beginPath(); ctx.arc(e.x, e.y, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = sparkCol; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(e.x, e.y, r, 0, Math.PI * 2); ctx.stroke();
  }
}

function draw() {
  requestAnimationFrame(draw);

  const st = lastState;
  if (!st) { drawWorld(); return; }

  // 화면 흔들림: 월드(배경+파이터+스파크)만 흔들고 HUD는 고정
  ctx.fillStyle = COLORS.black;
  ctx.fillRect(0, 0, W, H);
  let dx = 0, dy = 0;
  if (st.shake > 0) {
    const mag = SHAKE_MAG * Math.min(1, st.shake / SHAKE_SPECIAL);
    dx = (Math.random() * 2 - 1) * mag;
    dy = (Math.random() * 2 - 1) * mag;
  }
  ctx.save();
  ctx.translate(dx, dy);
  drawWorld();

  const [f1, f2] = st.fighters;
  drawFighter(f1, COLORS.p1, COLORS.p1Accent);
  drawFighter(f2, COLORS.p2, COLORS.p2Accent);
  drawEffects(st.effects || []);
  ctx.restore();

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
const roomFromUrl = params.get("room");
if (roomFromUrl) {
  // 링크로 들어온 참가자: 바로 join 시도 (연결 전이면 큐에 담김)
  setStatus("방 " + roomFromUrl.toUpperCase() + " 에 참가하는 중...");
  send({ t: "join", room: roomFromUrl });
} else {
  // 로비를 즉시 보여줘 콜드 스타트 중에도 버튼을 누를 수 있게 한다 (클릭은 큐에 담김)
  showLobby();
}
connect(() => {
  // 연결 완료 시점에 아직 로비 상태면(방을 아직 안 골랐으면) 안내만 갱신
  if (!mySide && !pendingSend && !roomFromUrl) showLobby();
});
draw();
