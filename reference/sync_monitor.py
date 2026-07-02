#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# sync_monitor.py - DEAD-MAN-SWITCH for file-sync peer connectivity (runs on the always-on hub).
#
# WHY: when sync silently dies, machines go mute and nobody notices for hours. This monitor
# watches the hub's live peer connections (Syncthing REST) and PINGS the group chat the MOMENT
# a peer drops -- so recovery starts in minutes, not after half a day. It is QUIET: it pings
# ONLY on a state CHANGE (connected->disconnected or back), never on every run. 0 LLM tokens
# (pure Python + the sync daemon's REST API).
#
# This is Layer 1 of the three self-heal layers (see docs/BUS.md):
#   Layer 1: this watchdog  -> detect + alert on a state change
#   Layer 2: auto-nudge     -> post a bounded number of group-chat lines telling the DOWN peer's
#                              robot to restart its own sync daemon (remote restart is impossible;
#                              the peer must heal itself, so tell ITS robot, not the human)
#   Layer 3: auto-failover  -> machine_bus.py mirrors messages to the chat rail while a peer is dark
#
# Run every ~20 min via a scheduled task / cron (a continuous safety monitor).
# State in ~/.machine-bus-monitor/state.json (local, not synced).
#
# Env: SYNC_APIKEY (the sync daemon's API key), SYNC_API (default http://127.0.0.1:8384/rest),
#      MACHINE_BUS_DIR (for machines.json), MACHINE_KEY (this machine's bus key),
#      BUS_RAIL2_CMD (command posting one text arg to the group chat),
#      CONFLICT_SWEEPER_CMD (optional: fired on peer reconnect to clean sync-conflict files).
import os, sys, json, time, shlex, subprocess, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".machine-bus-monitor")
STATE = os.path.join(STATE_DIR, "state.json")
LOG = os.path.join(STATE_DIR, "monitor.log")

API = os.environ.get("SYNC_API", "http://127.0.0.1:8384/rest")
APIKEY = (os.environ.get("SYNC_APIKEY") or "").strip()
BUS_DIR = os.environ.get("MACHINE_BUS_DIR", os.path.join(HOME, "machine-bus"))
ME_HUB = os.environ.get("MACHINE_KEY", os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "HUB-1"))).strip()

REPING_AFTER = 3 * 3600        # if a peer stays down, re-nag the human at most every 3h
NUDGE_EVERY = 30 * 60          # space auto group-nudges >= 30 min apart
NUDGE_MAX = 3                  # ... and at most 3 per down-episode, then rely on the 3h re-ping -> bounded noise


def _log(msg):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg + "\n")
    except Exception:
        pass


def _api(path):
    req = urllib.request.Request(API + path, headers={"X-API-Key": APIKEY})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def _chat_post(text):
    """Post one line to the group chat (rail 2). All monitor alerts go to the GROUP the humans
    already read, not to a private log nobody opens. Best-effort."""
    raw = (os.environ.get("BUS_RAIL2_CMD") or "").strip()
    if not raw:
        print("chat rail not configured (BUS_RAIL2_CMD); alert only logged:", text)
        _log("NO-RAIL2: " + text)
        return
    try:
        subprocess.run(shlex.split(raw) + [text], timeout=90)
    except Exception as e:
        print("ping failed:", e)


def _sweep_conflicts():
    # On a peer reconnect, divergent edits from the split surface as sync-conflict files ->
    # fire an optional loss-free sweeper (archive-first) so they self-heal, not pile up.
    raw = (os.environ.get("CONFLICT_SWEEPER_CMD") or "").strip()
    if not raw:
        return
    try:
        subprocess.Popen(shlex.split(raw),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _log("triggered conflict sweeper on peer reconnect")
    except Exception as e:
        _log(f"sweep trigger failed: {e}")


def _buskeys():
    """deviceID -> bus key (the name the peer's robot answers to), from machines.json.
    A nudge must address the peer by THIS, not the sync-daemon device name, or the peer's
    chat-rail filter won't match."""
    try:
        with open(os.path.join(BUS_DIR, "machines.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
        return {v.get("deviceID"): k for k, v in reg.get("machines", {}).items() if v.get("deviceID")}
    except Exception:
        return {}


def _group_nudge(buskey, down_min):
    """Layer-2 self-heal: post a 0-LLM group line telling a disconnected peer to restart its
    sync daemon. Best-effort -- the rail may be absent on a peer, never blocks the monitor."""
    mid = os.urandom(4).hex()
    text = ("\U0001F916 [%s -> %s] AUTO sync-link down ~%dmin -- your sync daemon is NOT connected "
            "to the hub (hub healthy). Restart your sync daemon via your watchdog task, then it "
            "self-reconnects. #%s" % (ME_HUB, buskey, down_min, mid))
    try:
        _chat_post(text)
        _log(f"group_nudge -> {buskey} (~{down_min}min)")
    except Exception as e:
        _log(f"group_nudge failed for {buskey}: {e}")


def main():
    if not APIKEY:
        print("SYNC_APIKEY not set -> cannot query the sync daemon; skip"); _log("SKIP: SYNC_APIKEY not set"); return
    try:
        names = {d["deviceID"]: d.get("name", d["deviceID"][:7]) for d in _api("/config/devices")}
        conns = _api("/system/connections").get("connections", {})
        myid = _api("/system/status").get("myID", "")
    except Exception as e:
        print("sync daemon API unreachable:", e)
        # The daemon itself may be down -> that's its own watchdog's job; we only watch PEERS here.
        return

    state = _load_state()
    buskeys = _buskeys()
    now = int(time.time())
    changed = []
    for dev, c in conns.items():
        if dev == myid:
            continue
        name = names.get(dev, dev[:7])
        bk = buskeys.get(dev)
        cur = bool(c.get("connected"))
        prev = state.get(dev)
        if prev is None:
            # first time we see this peer -> record baseline, do NOT alert (avoid spurious first-run ping).
            # last_alert=now (not 0) so a peer that is ALREADY down at baseline doesn't instantly re-nag.
            state[dev] = {"connected": cur, "since": now, "last_alert": now if not cur else 0, "nudges": 0, "last_nudge": 0}
            continue
        was = prev.get("connected")
        if cur != was:
            # transition
            if cur:
                _chat_post(f"✅ SYNC OK: {name} reconnected to the hub. Full fleet is converging.")
                _sweep_conflicts()  # peer back -> auto-clear any conflicts the split produced
                state[dev] = {"connected": True, "since": now, "last_alert": 0, "nudges": 0, "last_nudge": 0}
            else:
                _chat_post(f"\U0001F50C SYNC ALERT: {name} DROPPED off the hub. Possible sync loss; see your sync-loss runbook. Coordinate on the bus.")
                nud, lastn = 0, 0
                if bk:  # Layer-2: first auto-nudge to the peer's robot to restart its sync daemon
                    _group_nudge(bk, 1); nud, lastn = 1, now
                state[dev] = {"connected": False, "since": now, "last_alert": now, "nudges": nud, "last_nudge": lastn}
            changed.append((name, cur))
        elif not cur:
            # still down: (a) bounded auto-nudges every NUDGE_EVERY up to NUDGE_MAX, (b) human re-nag every REPING_AFTER
            since = prev.get("since", now)
            if bk and prev.get("nudges", 0) < NUDGE_MAX and now - prev.get("last_nudge", 0) >= NUDGE_EVERY:
                _group_nudge(bk, max(1, round((now - since) / 60)))
                prev["nudges"] = prev.get("nudges", 0) + 1
                prev["last_nudge"] = now
            if now - prev.get("last_alert", 0) >= REPING_AFTER:
                down_h = round((now - since) / 3600, 1)
                _chat_post(f"⏳ SYNC still down: {name} offline ~{down_h}h. Raise it per your sync-loss runbook.")
                prev["last_alert"] = now
            state[dev] = prev
        else:
            state[dev] = {"connected": True, "since": prev.get("since", now), "last_alert": 0, "nudges": 0, "last_nudge": 0}

    _save_state(state)
    online = sum(1 for d, c in conns.items() if d != myid and c.get("connected"))
    total = sum(1 for d in conns if d != myid)
    print(f"sync_monitor: {online}/{total} peers connected; changes this run: {changed or 'none'}")
    _log(f"{online}/{total} peers connected; changes: {changed or 'none'}")


if __name__ == "__main__":
    main()
