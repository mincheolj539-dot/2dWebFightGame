"""레이팅(Elo) 저장소 — 매칭 시스템용.

게임 로직이 아니라 서버 메타 데이터라 Match 와 분리한다.
플레이어 식별은 브라우저가 만든 UUID(pid). 계정/비밀번호는 없다.
"""

import json
import os
import tempfile

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
PATH = os.path.join(DATA_DIR, "ratings.json")

START = 1000          # 시작 레이팅
K = 32                # Elo K-factor (변동 폭)
MAX_ENTRIES = 20000   # 저장소 상한 (무한 증가 방지)

_store = None         # pid -> {"r": int, "n": str, "w": int, "l": int}


def _load():
    global _store
    if _store is not None:
        return _store
    try:
        with open(PATH, encoding="utf-8") as f:
            _store = json.load(f)
    except (OSError, json.JSONDecodeError):
        _store = {}
    return _store


def _save():
    """원자적 저장 — 쓰다가 죽어도 기존 파일이 깨지지 않게 임시파일 후 교체."""
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False)
        os.replace(tmp, PATH)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def get(pid, name=None):
    """플레이어 기록 조회(없으면 생성). name 이 오면 갱신."""
    store = _load()
    entry = store.get(pid)
    if entry is None:
        if len(store) >= MAX_ENTRIES:
            return {"r": START, "n": name or "", "w": 0, "l": 0}   # 저장 없이 임시 취급
        entry = {"r": START, "n": name or "", "w": 0, "l": 0}
        store[pid] = entry
    if name:
        entry["n"] = name
    return entry


def _expected(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def record(pid_a, pid_b, score_a):
    """대전 결과 반영. score_a 는 A 기준 1.0(승)/0.0(패). (old_a, new_a, old_b, new_b) 반환."""
    a, b = get(pid_a), get(pid_b)
    ra, rb = a["r"], b["r"]
    na = round(ra + K * (score_a - _expected(ra, rb)))
    nb = round(rb + K * ((1.0 - score_a) - _expected(rb, ra)))
    a["r"], b["r"] = na, nb
    if score_a >= 1.0:
        a["w"] += 1
        b["l"] += 1
    else:
        a["l"] += 1
        b["w"] += 1
    _save()
    return ra, na, rb, nb
