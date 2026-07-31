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
  spark: "rgb(255,240,190)",
  counter: "rgb(255,220,70)",
  guardGauge: "rgb(120,220,255)", guardLow: "rgb(255,120,90)", guardBreak: "rgb(255,80,170)",
  dust: "rgb(150,150,165)",
};
const SHAKE_MAG = 9, SHAKE_SPECIAL = 14;  // settings.py와 동기화

// ---- 키 → 액션 매핑 ----
// 온라인: 내 파이터 하나만 조작하므로 WASD와 방향키 둘 다 자신에게 매핑.
const KEYMAP = {
  KeyA: "left", ArrowLeft: "left",
  KeyD: "right", ArrowRight: "right",
  KeyW: "jump", ArrowUp: "jump",
  KeyS: "down", ArrowDown: "down",
  KeyF: "attack", Period: "attack",
  KeyG: "block", Slash: "block",
};
// 로컬 2인(한 화면): 1P = WASD + F/G, 2P = 방향키 + 넘패드 1/2
const KEYMAP_LOCAL = {
  P1: { KeyA: "left", KeyD: "right", KeyW: "jump", KeyS: "down", KeyF: "attack", KeyG: "block" },
  P2: { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "jump", ArrowDown: "down",
        Numpad1: "attack", Numpad2: "block" },
};

// ---- DOM ----
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const overlay = document.getElementById("overlay");
const statusEl = document.getElementById("status");
const lobbyEl = document.getElementById("lobby");
const shareEl = document.getElementById("share");
const copyBtn = document.getElementById("btn-copy");
const nickEl = document.getElementById("nick");
const myRatingEl = document.getElementById("my-rating");
const cancelBtn = document.getElementById("btn-cancel");

// ---- 연결 상태 ----
// 로컬 2인 모드는 한 페이지에서 소켓을 2개 열어 같은 방의 P1/P2 로 접속한다.
// (게임 로직은 서버 Match 하나에만 있고, 여기선 키를 어느 소켓으로 보낼지만 나눈다.)
let ws = null;        // 주 소켓 — P1 조작 + 화면에 그릴 상태 수신
let ws2 = null;       // 로컬 2인 모드에서 P2 조작용 보조 소켓
let localMode = false;
let mySide = null;
let lastState = null;
let started = false;

// ---- 레이팅 대전 ----
// 계정이 없으므로 플레이어 식별은 브라우저에 저장한 임의 ID로 한다.
// (저장소를 지우면 새 플레이어가 되고 점수도 초기화된다.)
let ranked = null;            // {me:{name,rating}, opp:{name,rating}} — 매칭되면 채워짐
let ratingResult = null;      // {old,new,delta} — 매치 종료 후 서버가 알려줌

function playerId() {
  let id = localStorage.getItem("fightPlayerId");
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) ||
         String(Date.now()) + Math.random().toString(36).slice(2);
    localStorage.setItem("fightPlayerId", id);
  }
  return id;
}

const params = new URLSearchParams(location.search);
const SERVER = params.get("server") || window.GAME_SERVER;

function setStatus(text) { statusEl.textContent = text; }

function showLobby() {
  lobbyEl.style.display = "block";
  nickEl.value = localStorage.getItem("fightName") || "";
  const r = localStorage.getItem("fightRating");
  myRatingEl.textContent = r ? "내 레이팅 " + r : "";
  setStatus("레이팅 대전을 하거나, 방을 만들어 친구와 하세요");
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
      if (localMode) {
        // 방이 만들어졌으니 같은 방에 2P 소켓을 붙인다 → 서버가 두 명으로 보고 시작.
        setStatus("로컬 대전 준비 중...");
        connectLocalP2(msg.code);
      } else if (mySide === "P1") {
        lobbyEl.style.display = "none";
        shareEl.style.display = "block";
        copyBtn.style.display = "inline-block";
        shareEl.textContent = shareUrl(msg.code);
        setStatus("방 코드: " + msg.code + " — 친구가 접속하길 기다리는 중...");
      } else {
        setStatus("참가 완료! 곧 시작합니다...");
      }
    } else if (msg.t === "queued") {
      lobbyEl.style.display = "none";
      cancelBtn.style.display = "inline-block";
      setStatus("상대를 찾는 중... (내 레이팅 " + msg.rating + " · 대기 " + msg.waiting + "명)");
    } else if (msg.t === "matched") {
      mySide = msg.side;
      ranked = { me: msg.me, opp: msg.opp };
      ratingResult = null;
      cancelBtn.style.display = "none";
      setStatus("매칭 완료! " + msg.opp.name + " (" + msg.opp.rating + ")");
    } else if (msg.t === "rating") {
      ratingResult = msg;
      if (ranked) ranked.me.rating = msg.new;
      localStorage.setItem("fightRating", msg.new);
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
      cancelBtn.style.display = "none";
      setStatus(localMode ? "연결이 끊어졌습니다. 새로고침해서 다시 시작하세요."
                          : "상대가 나갔습니다. 새로고침해서 다시 시작하세요.");
    } else if (msg.t === "error") {
      setStatus(msg.msg);
      lobbyEl.style.display = "block";
    }
  };
}

// 로컬 2인 모드 전용: 같은 방에 2P 로 참가하는 보조 소켓.
// 상태 스냅샷은 주 소켓 것만 그리므로 여기선 수신 메시지를 쓰지 않는다.
function connectLocalP2(code) {
  ws2 = new WebSocket(SERVER);
  ws2.onopen = () => ws2.send(JSON.stringify({ t: "join", room: code }));
  ws2.onclose = () => {
    if (!started) setStatus("2P 연결에 실패했습니다. 새로고침해서 다시 시도하세요.");
  };
}

// 소켓이 아직 열리지 않았으면 보류했다가 open 시 전송.
let pendingSend = null;
function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  else pendingSend = obj;              // 방 생성/참가 클릭이 연결 전에 눌린 경우
}
function sendTo(sock, obj) {           // 키 입력은 큐에 담지 않는다 (지난 입력은 무의미)
  if (sock && sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify(obj));
}
function flushPending() {
  if (pendingSend && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(pendingSend));
    pendingSend = null;
  }
}

// ---- 로비 UI ----
// 아직 연결 전이면 클릭을 큐에 담고 연결 중임을 알린다.
const connecting = () => !(ws && ws.readyState === WebSocket.OPEN);
document.getElementById("btn-rank").onclick = () => {
  const name = nickEl.value.trim() || "익명";
  localStorage.setItem("fightName", name);
  lobbyEl.style.display = "none";
  setStatus(connecting() ? "서버에 연결하는 중..." : "상대를 찾는 중...");
  send({ t: "queue", id: playerId(), name: name });
};
cancelBtn.onclick = () => {
  send({ t: "cancel" });
  cancelBtn.style.display = "none";
  showLobby();
};
document.getElementById("btn-create").onclick = () => {
  lobbyEl.style.display = "none";
  setStatus(connecting() ? "서버에 연결하는 중..."
                         : "방을 만드는 중...");
  send({ t: "create" });              // 연결 전이면 큐에 담겨 열릴 때 자동 전송
};
document.getElementById("btn-local").onclick = () => {
  localMode = true;
  lobbyEl.style.display = "none";
  setStatus(connecting() ? "서버에 연결하는 중..."
                         : "로컬 대전 준비 중...");
  send({ t: "create" });              // 방이 만들어지면 2P 소켓이 자동으로 참가
};
document.getElementById("btn-join").onclick = () => {
  const code = document.getElementById("room-input").value.trim().toUpperCase();
  if (code.length !== 4) return;
  setStatus(connecting() ? "서버에 연결하는 중..."
                         : "방 " + code + " 에 참가하는 중...");
  send({ t: "join", room: code });
};
copyBtn.onclick = () => {
  navigator.clipboard.writeText(shareEl.textContent);
  copyBtn.textContent = "복사됨!";
  setTimeout(() => (copyBtn.textContent = "링크 복사"), 1500);
};

// ---- 키 입력 ----
// 로컬 2인 모드에선 키가 속한 플레이어의 소켓으로 보낸다.
function routeKey(e, down) {
  if (localMode) {
    const a1 = KEYMAP_LOCAL.P1[e.code];
    if (a1) { e.preventDefault(); sendTo(ws, { t: "key", a: a1, d: down }); return; }
    const a2 = KEYMAP_LOCAL.P2[e.code];
    if (a2) { e.preventDefault(); sendTo(ws2, { t: "key", a: a2, d: down }); }
    return;
  }
  const action = KEYMAP[e.code];
  if (action) { e.preventDefault(); sendTo(ws, { t: "key", a: action, d: down }); }
}
window.addEventListener("keydown", (e) => {
  if (e.repeat) return;                       // 커맨드 판정에 자동 반복 입력 금지
  if (e.code === "KeyR") { send({ t: "restart" }); return; }
  routeKey(e, true);
});
window.addEventListener("keyup", (e) => routeKey(e, false));

// ---- 렌더링 (데스크톱 game.py draw 와 동일한 모양) ----
const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
bgGrad.addColorStop(0, COLORS.bgTop);
bgGrad.addColorStop(1, COLORS.bgBottom);

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function drawFighter(f, color, accent) {
  const bx = f.bx, by = f.by, bw = f.bw, bh = f.bh, sk = f.skel;
  // 상태 오라 (몸 뒤)
  if (f.counter > 0 && Math.floor(f.counter / 3) % 2 === 0) {
    ctx.fillStyle = COLORS.counter;
    roundRect(bx - 8, by - 8, bw + 16, bh + 16, 14); ctx.fill();
  }
  // 몸 색 (가드브레이크 마젠타 깜빡 > 피격 흰색 > 기본)
  const gb = f.guard_break || 0;
  let bodyCol;
  if (gb > 0 && Math.floor(gb / 4) % 2 === 0) bodyCol = COLORS.guardBreak;
  else bodyCol = f.flash ? COLORS.white : color;

  const lw = sk.lw, jr = sk.joint;
  function limb(pts) {
    ctx.strokeStyle = bodyCol; ctx.fillStyle = bodyCol;
    ctx.lineWidth = lw; ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.stroke();
    // 손/발 강조
    const end = pts[pts.length - 1];
    ctx.fillStyle = accent;
    ctx.beginPath(); ctx.arc(end[0], end[1], jr, 0, Math.PI * 2); ctx.fill();
  }
  const poly = (pts, fill, stroke, sw) => {
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = sw; ctx.stroke(); }
  };

  // 뒤쪽 팔·다리 → 몸통 → 머리 → 앞쪽 다리·팔
  limb(sk.arm_b);
  limb(sk.leg_b);
  poly(sk.torso, bodyCol, accent, 2);
  const [hx, hy, hr] = sk.head;
  ctx.fillStyle = bodyCol; ctx.beginPath(); ctx.arc(hx, hy, hr, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = accent; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(hx, hy, hr, 0, Math.PI * 2); ctx.stroke();
  limb(sk.leg_f);
  limb(sk.arm_f);

  // 상태 외곽선
  if (f.hurt > 0) { ctx.strokeStyle = COLORS.spark; ctx.lineWidth = 2; roundRect(bx - 3, by - 3, bw + 6, bh + 6, 10); ctx.stroke(); }
  if (gb > 0) { ctx.strokeStyle = COLORS.guardBreak; ctx.lineWidth = 3; roundRect(bx - 5, by - 5, bw + 10, bh + 10, 12); ctx.stroke(); }
  if (f.counter > 0) { ctx.strokeStyle = COLORS.counter; ctx.lineWidth = 3; roundRect(bx - 4, by - 4, bw + 8, bh + 8, 11); ctx.stroke(); }

  // 눈
  ctx.fillStyle = COLORS.black;
  ctx.beginPath(); ctx.arc(f.eye[0], f.eye[1], Math.max(3, Math.floor(hr / 3)), 0, Math.PI * 2); ctx.fill();
  // 공격 임팩트(주먹/발) 강조 원
  if (f.fist) {
    ctx.fillStyle = COLORS.attack;
    ctx.beginPath(); ctx.arc(f.fist.x, f.fist.y, f.fist.r, 0, Math.PI * 2); ctx.fill();
  }
  // 가드
  if (f.guard) {
    ctx.fillStyle = COLORS.block;
    roundRect(f.guard.x, f.guard.y, f.guard.w, f.guard.h, 4); ctx.fill();
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

function drawGuardGauge(f, x, alignLeft) {
  const w = 360, h = 6, y = 53;
  ctx.fillStyle = COLORS.black;
  roundRect(x - 2, y - 2, w + 4, h + 4, 3); ctx.fill();
  ctx.fillStyle = COLORS.grey;
  roundRect(x, y, w, h, 2); ctx.fill();
  const ratio = Math.max(0, Math.min(1, f.guard_gauge || 0));  // 0..1 (서버 계산)
  const fillW = Math.floor(w * ratio);
  if (fillW > 0) {
    ctx.fillStyle = (f.guard_locked || ratio < 0.25) ? COLORS.guardLow : COLORS.guardGauge;
    roundRect(alignLeft ? x : x + w - fillW, y, fillW, h, 2);
    ctx.fill();
  }
}

// 레이팅 대전이면 "P1/P2" 대신 닉네임+점수를 쓴다.
function sideLabel(side) {
  if (!ranked || (side !== "P1" && side !== "P2")) return side;
  const p = (mySide === side) ? ranked.me : ranked.opp;
  return p.name + " " + p.rating;
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

function drawGuardBreak(e, grow) {
  // 가드 브레이크 전용: 확산하는 마젠타 링 + 파편
  const ringR = 18 + grow * 46;
  ctx.strokeStyle = COLORS.guardBreak; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.arc(e.x, e.y, ringR, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = COLORS.white; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(e.x, e.y, Math.max(2, ringR - 8), 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = COLORS.guardBreak; ctx.lineWidth = 3;
  for (let i = 0; i < 8; i++) {
    const ang = Math.PI * i / 4 + grow * 0.5;
    const d = 14 + grow * 40;
    ctx.beginPath();
    ctx.moveTo(e.x + Math.cos(ang) * 10, e.y + Math.sin(ang) * 10);
    ctx.lineTo(e.x + Math.cos(ang) * d, e.y + Math.sin(ang) * d);
    ctx.stroke();
  }
}

function drawEffects(effects) {
  // 임팩트: 맞은 자리에 확산하는 링 + 밝은 원 (동그란 타격 이펙트)
  for (const e of effects) {
    const grow = 1 - e.t;
    if (e.kind === "guardbreak") { drawGuardBreak(e, grow); continue; }
    if (e.kind === "dust") {
      ctx.fillStyle = COLORS.dust;
      for (const k of [-1, 0, 1]) {
        const pr = Math.max(1, (5 - Math.abs(k)) * e.t);
        ctx.beginPath();
        ctx.arc(e.x + k * grow * 22, e.y - grow * 8, pr, 0, Math.PI * 2);
        ctx.fill();
      }
      continue;
    }
    const sparkCol = e.block ? COLORS.block : COLORS.spark;  // 가드 시 파란색
    const base = e.big ? 16 : 11;
    const ringR = base * (0.5 + grow * 1.4);
    ctx.strokeStyle = sparkCol; ctx.lineWidth = e.big ? 4 : 3;
    ctx.beginPath(); ctx.arc(e.x, e.y, ringR, 0, Math.PI * 2); ctx.stroke();
    const core = base * (0.4 + e.t * 0.7);
    if (core > 0) {
      ctx.fillStyle = COLORS.white;
      ctx.beginPath(); ctx.arc(e.x, e.y, core, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = sparkCol; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(e.x, e.y, core, 0, Math.PI * 2); ctx.stroke();
    }
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
  drawGuardGauge(f1, 30, true);
  drawGuardGauge(f2, W - 30 - 360, false);
  ctx.fillStyle = COLORS.white;
  ctx.font = "bold 18px Consolas, monospace";
  ctx.textAlign = "left";
  // 로컬 2인 모드는 누가 어느 키인지, 온라인은 어느 쪽이 나인지 표시
  const tag1 = localMode ? "  (WASD)" : (mySide === "P1" ? "  (YOU)" : "");
  const tag2 = localMode ? "(방향키)  " : (mySide === "P2" ? "(YOU)  " : "");
  ctx.fillText(sideLabel("P1") + " " + "●".repeat(st.wins.P1) + tag1, 30, 74);
  ctx.textAlign = "right";
  ctx.fillText(tag2 + "●".repeat(st.wins.P2) + " " + sideLabel("P2"), W - 30, 74);
  ctx.textAlign = "center";
  ctx.font = "bold 30px Consolas, monospace";
  ctx.fillText(String(st.time), W / 2, 64);

  // 특수기 팝업
  if (st.popup) {
    ctx.fillStyle = COLORS.attack;
    ctx.font = "bold 30px Consolas, monospace";
    ctx.fillText(st.popup, W / 2, 130);
  }

  // 라운드/매치 종료 표시 (레이팅 대전이면 점수 변동도 함께)
  if (st.match_over) {
    let sub = "R 키로 재시작";
    if (ratingResult) {
      const d = ratingResult.delta;
      sub = "레이팅 " + ratingResult.new + " (" + (d >= 0 ? "+" : "") + d + ")  ·  " + sub;
    }
    drawCenterText(sideLabel(st.match_winner) + " WINS THE MATCH!", sub);
  } else if (st.round_over) {
    drawCenterText(st.round_winner === "DRAW" ? "DRAW"
                                              : sideLabel(st.round_winner) + " WINS ROUND", null);
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
