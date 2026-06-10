#!/usr/bin/env python3
"""
AuziTrack backend — reads dump1090 aircraft.json, enriches with
route lookups via api.adsbdb.com, and serves /aircraft on port 5000.
"""

import json
import time
import threading
import logging
import requests
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

# ── Config ────────────────────────────────────────────────────────────────────

AIRCRAFT_JSON = Path(
    "/home/auziman/projects/flight-tracker-antenna/dump1090/public_html/aircraft.json"
)
ADSBDB_URL    = "https://api.adsbdb.com/v0/callsign"
REFRESH_SEC   = 1
ROUTE_CACHE_TTL = 3600  # seconds before a cached route is re-fetched
LOOKUP_TIMEOUT  = 8     # seconds before giving up on a route request

# ── Shared state ──────────────────────────────────────────────────────────────

_state_lock = threading.Lock()
_state = {"aircraft": [], "now": 0, "messages": 0}

# callsign → {"origin": str|None, "dest": str|None, "pending": bool, "cached_at": float}
_route_cache: dict[str, dict] = {}
_route_lock = threading.Lock()

log = logging.getLogger("tracker")

# ── Route lookup ──────────────────────────────────────────────────────────────

def _fetch_route(callsign: str) -> None:
    """Background thread: query adsbdb.com and populate route cache."""
    origin = dest = None
    try:
        r = requests.get(f"{ADSBDB_URL}/{callsign}", timeout=LOOKUP_TIMEOUT)
        if r.status_code == 200:
            route = r.json().get("response", {}).get("flightroute", {})
            if route:
                o = route.get("origin", {})
                d = route.get("destination", {})
                origin = o.get("municipality") or o.get("icao_code")
                dest   = d.get("municipality") or d.get("icao_code")
        elif r.status_code not in (404, 204):
            log.warning("adsbdb %s returned HTTP %s", callsign, r.status_code)
    except Exception as e:
        log.warning("adsbdb lookup failed for %s: %s", callsign, e)

    with _route_lock:
        _route_cache[callsign] = {
            "origin": origin,
            "dest": dest,
            "pending": False,
            "cached_at": time.time(),
        }


def _get_route(callsign: str) -> tuple[str | None, str | None, bool]:
    """
    Return (origin, dest, pending). pending=True while the lookup is in flight.
    Queues a background fetch on first call; subsequent calls read from cache.
    """
    now = time.time()
    with _route_lock:
        cached = _route_cache.get(callsign)
        if cached and (now - cached["cached_at"]) < ROUTE_CACHE_TTL:
            return cached["origin"], cached["dest"], cached["pending"]
        # Mark pending before releasing the lock so concurrent refreshes don't double-queue
        _route_cache[callsign] = {"origin": None, "dest": None, "pending": True, "cached_at": now}

    threading.Thread(target=_fetch_route, args=(callsign,), daemon=True).start()
    return None, None, True


# ── Refresh loop ──────────────────────────────────────────────────────────────

def _refresh_loop() -> None:
    while True:
        try:
            with open(AIRCRAFT_JSON) as f:
                raw = json.load(f)

            enriched = []
            for ac in raw.get("aircraft", []):
                ac = dict(ac)
                callsign = (ac.get("flight") or "").strip()
                if callsign:
                    ac["origin"], ac["dest"], ac["route_pending"] = _get_route(callsign)
                else:
                    ac["origin"] = ac["dest"] = None
                    ac["route_pending"] = False
                enriched.append(ac)

            with _state_lock:
                _state["aircraft"] = enriched
                _state["now"] = raw.get("now", time.time())
                _state["messages"] = raw.get("messages", 0)

        except Exception as e:
            log.warning("refresh error: %s", e)

        time.sleep(REFRESH_SEC)


# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("werkzeug").setLevel(logging.WARNING)


@app.route("/aircraft")
def get_aircraft():
    with _state_lock:
        return jsonify(dict(_state))


@app.route("/health")
def health():
    return "ok"


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=_refresh_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
