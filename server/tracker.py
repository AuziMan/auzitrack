#!/usr/bin/env python3
"""
AuziTrack backend — reads dump1090 aircraft.json, enriches with
OpenSky route lookups, and serves /aircraft on port 5000.
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
OPENSKY_ROUTES_URL = "https://opensky-network.org/api/routes"
REFRESH_SEC = 1
ROUTE_CACHE_TTL = 3600   # seconds before a cached route is re-fetched
LOOKUP_TIMEOUT = 5       # seconds before giving up on an OpenSky request

# ── Airport name map (ICAO → city) ───────────────────────────────────────────

AIRPORTS = {
    "KABQ": "Albuquerque",  "KASE": "Aspen",        "KATL": "Atlanta",
    "KAUS": "Austin",       "KBDL": "Hartford",      "KBFI": "Seattle Boeing",
    "KBNA": "Nashville",    "KBOI": "Boise",         "KBOS": "Boston",
    "KBUR": "Burbank",      "KBWI": "Baltimore",     "KCHS": "Charleston",
    "KCLE": "Cleveland",    "KCLT": "Charlotte",     "KCOS": "Colorado Springs",
    "KCVG": "Cincinnati",   "KDAL": "Dallas Love",   "KDCA": "Washington Reagan",
    "KDEN": "Denver",       "KDFW": "Dallas DFW",    "KDTW": "Detroit",
    "KELP": "El Paso",      "KEWR": "Newark",        "KFAT": "Fresno",
    "KFLL": "Fort Lauderdale", "KGEG": "Spokane",   "KHOU": "Houston Hobby",
    "KIAD": "Washington Dulles", "KIAH": "Houston IAH", "KIND": "Indianapolis",
    "KJAX": "Jacksonville", "KJFK": "New York JFK",  "KLAS": "Las Vegas",
    "KLAX": "Los Angeles",  "KLGA": "New York LGA",  "KLGB": "Long Beach",
    "KMCI": "Kansas City",  "KMCO": "Orlando",       "KMDW": "Chicago Midway",
    "KMEM": "Memphis",      "KMIA": "Miami",         "KMKE": "Milwaukee",
    "KMSP": "Minneapolis",  "KMSY": "New Orleans",   "KOAK": "Oakland",
    "KOMA": "Omaha",        "KONT": "Ontario",       "KORD": "Chicago O'Hare",
    "KPDX": "Portland",     "KPHL": "Philadelphia",  "KPHX": "Phoenix",
    "KPIT": "Pittsburgh",   "KRDU": "Raleigh",       "KRIC": "Richmond",
    "KRNO": "Reno",         "KRSW": "Fort Myers",    "KSAN": "San Diego",
    "KSAT": "San Antonio",  "KSAV": "Savannah",      "KSDF": "Louisville",
    "KSEA": "Seattle",      "KSFO": "San Francisco", "KSJC": "San Jose",
    "KSLC": "Salt Lake City", "KSMF": "Sacramento",  "KSNA": "Orange County",
    "KSTL": "St. Louis",    "KTPA": "Tampa",         "KTUL": "Tulsa",
    "KTUS": "Tucson",
}


def airport_label(icao: str) -> str:
    """Return city name if known, otherwise the ICAO code."""
    return AIRPORTS.get(icao, icao)


# ── Shared state ──────────────────────────────────────────────────────────────

_state_lock = threading.Lock()
_state = {"aircraft": [], "now": 0, "messages": 0}

# callsign → {"origin": str|None, "dest": str|None, "cached_at": float}
_route_cache: dict[str, dict] = {}
_route_lock = threading.Lock()

# ── OpenSky lookup ────────────────────────────────────────────────────────────

def _fetch_route(callsign: str) -> None:
    """Background thread: query OpenSky and populate route cache."""
    origin = dest = None
    try:
        r = requests.get(
            OPENSKY_ROUTES_URL,
            params={"callsign": callsign},
            timeout=LOOKUP_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            route = data.get("route", [])
            if len(route) >= 2:
                origin = airport_label(route[0])
                dest = airport_label(route[-1])
    except Exception:
        pass

    with _route_lock:
        _route_cache[callsign] = {
            "origin": origin,
            "dest": dest,
            "cached_at": time.time(),
        }


def _get_route(callsign: str) -> tuple[str | None, str | None]:
    """
    Return cached (origin, dest). If not cached or stale, queue a background
    lookup and return (None, None) for this cycle — result appears next refresh.
    """
    now = time.time()
    with _route_lock:
        cached = _route_cache.get(callsign)
        if cached:
            if (now - cached["cached_at"]) < ROUTE_CACHE_TTL:
                return cached["origin"], cached["dest"]
        # Mark as pending immediately so concurrent refreshes don't double-queue
        _route_cache[callsign] = {"origin": None, "dest": None, "cached_at": now}

    threading.Thread(target=_fetch_route, args=(callsign,), daemon=True).start()
    return None, None


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
                    ac["origin"], ac["dest"] = _get_route(callsign)
                else:
                    ac["origin"] = ac["dest"] = None
                enriched.append(ac)

            with _state_lock:
                _state["aircraft"] = enriched
                _state["now"] = raw.get("now", time.time())
                _state["messages"] = raw.get("messages", 0)

        except Exception:
            pass

        time.sleep(REFRESH_SEC)


# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)
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
