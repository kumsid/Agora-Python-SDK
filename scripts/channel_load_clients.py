#!/usr/bin/env python3
"""
Spawn many Agora RTC clients that join one channel and receive remote audio/video.

Each client runs in its own process (recommended for this native SDK). Configure
via a `.env` file in the repository root (see `.env.example`) or environment variables.

One worker (default: client index 0) prints aggregate receive/transmit bytes from
`onRtcStats` about every 2 seconds. Every worker appends the same metrics (plus
`leave` totals) to its own CSV under `RTC_STATS_CSV_DIR` (default `rtc_stats_logs/`).

Scaling: thousands of real RTC peers need many hosts and Agora-approved load
patterns; one laptop cannot safely simulate 5k full SDK clients (RAM, CPU,
file descriptors, and decode load).

On Apple Silicon with the v3.1.2 x86_64 SDK build, run Python under Rosetta, e.g.:
  cd /path/to/Agora-Python-SDK && arch -x86_64 .venv/bin/python scripts/channel_load_clients.py
"""

from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATS_CSV_FIELDS = (
    "timestamp_utc",
    "event",
    "worker_label",
    "client_index",
    "agora_uid",
    "channel",
    "rx_bytes",
    "tx_bytes",
    "rx_audio_bytes",
    "rx_video_bytes",
    "tx_audio_bytes",
    "tx_video_bytes",
    "rx_kbit_rate",
    "tx_kbit_rate",
    "duration_s",
    "user_count",
)


def _append_stats_csv(csv_path: str, row: dict[str, object]) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=STATS_CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)
        f.flush()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from `.env` into os.environ (does not override existing vars)."""
    env_path = path or (_repo_root() / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _stats_csv_row(
    event: str,
    stats: Any,
    worker_label: str,
    client_index: int,
    agora_uid: int,
    channel_name: str,
) -> dict[str, object]:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "worker_label": worker_label,
        "client_index": client_index,
        "agora_uid": agora_uid,
        "channel": channel_name,
        "rx_bytes": stats.rxBytes,
        "tx_bytes": stats.txBytes,
        "rx_audio_bytes": stats.rxAudioBytes,
        "rx_video_bytes": stats.rxVideoBytes,
        "tx_audio_bytes": stats.txAudioBytes,
        "tx_video_bytes": stats.txVideoBytes,
        "rx_kbit_rate": stats.rxKBitRate,
        "tx_kbit_rate": stats.txKBitRate,
        "duration_s": stats.duration,
        "user_count": stats.userCount,
    }


def _worker(cfg: dict) -> None:
    root = Path(cfg["repo_root"])
    os.chdir(root)
    rp = str(root)
    if rp not in sys.path:
        sys.path.insert(0, rp)

    import agorartc

    uid = int(cfg["uid"])
    client_index = int(cfg["client_index"])
    app_id = cfg["app_id"]
    token = cfg["token"] or ""
    channel = cfg["channel"]
    duration = float(cfg["duration_sec"])
    role = cfg["role"]
    label = cfg["label"]
    log_periodic_rx = bool(cfg.get("log_periodic_rx"))
    stats_csv_path = cfg.get("stats_csv_path")

    class Handler(agorartc.RtcEngineEventHandlerBase):
        def __init__(self) -> None:
            super().__init__()

        def onRtcStats(self, stats: agorartc.RtcStats) -> None:
            if stats_csv_path:
                _append_stats_csv(
                    stats_csv_path,
                    _stats_csv_row("rtc_stats", stats, label, client_index, uid, channel),
                )
            if log_periodic_rx:
                print(
                    f"[{label}] onRtcStats rxBytes={stats.rxBytes} txBytes={stats.txBytes} "
                    f"rxAudioBytes={stats.rxAudioBytes} rxVideoBytes={stats.rxVideoBytes} "
                    f"rxKBitRate={stats.rxKBitRate} duration_s={stats.duration} userCount={stats.userCount}"
                )
            super().onRtcStats(stats)

        def onJoinChannelSuccess(self, channel_name: str, u: int, elapsed: int) -> None:
            print(f"[{label}] onJoinChannelSuccess channel={channel_name} uid={u} elapsed={elapsed}ms")
            super().onJoinChannelSuccess(channel_name, u, elapsed)

        def onLeaveChannel(self, stats: agorartc.RtcStats) -> None:
            if stats_csv_path:
                _append_stats_csv(
                    stats_csv_path,
                    _stats_csv_row("leave", stats, label, client_index, uid, channel),
                )
            print(f"[{label}] onLeaveChannel duration={stats.duration}s tx={stats.txBytes} rx={stats.rxBytes}")
            super().onLeaveChannel(stats)

        def onUserJoined(self, u: int, elapsed: int) -> None:
            print(f"[{label}] onUserJoined remote_uid={u} elapsed={elapsed}ms")
            super().onUserJoined(u, elapsed)

        def onUserOffline(self, u: int, reason: int) -> None:
            print(f"[{label}] onUserOffline remote_uid={u} reason={reason}")
            super().onUserOffline(u, reason)

        def onRemoteVideoStateChanged(
            self, u: int, state: int, reason: int, elapsed: int
        ) -> None:
            print(f"[{label}] onRemoteVideoStateChanged uid={u} state={state} reason={reason}")
            super().onRemoteVideoStateChanged(u, state, reason, elapsed)

        def onRemoteAudioStateChanged(
            self, u: int, state: int, reason: int, elapsed: int
        ) -> None:
            print(f"[{label}] onRemoteAudioStateChanged uid={u} state={state} reason={reason}")
            super().onRemoteAudioStateChanged(u, state, reason, elapsed)

        def onError(self, err: int, msg: str) -> None:
            print(f"[{label}] onError err={err} msg={msg}")
            super().onError(err, msg)

    rtc = agorartc.createRtcEngineBridge()
    handler = Handler()
    rtc.initEventHandler(handler)

    area = agorartc.AREA_CODE_GLOB & 0xFFFFFFFF
    if rtc.initialize(app_id, None, area) != 0:
        print(f"[{label}] initialize failed", file=sys.stderr)
        return

    rtc.setChannelProfile(agorartc.CHANNEL_PROFILE_LIVE_BROADCASTING)
    if role == "broadcaster":
        rtc.setClientRole(agorartc.CLIENT_ROLE_BROADCASTER)
    else:
        rtc.setClientRole(agorartc.CLIENT_ROLE_AUDIENCE)

    rtc.enableVideo()
    rtc.enableAudio()

    if role != "broadcaster":
        rtc.muteLocalAudioStream(True)
        rtc.muteLocalVideoStream(True)

    ret = rtc.joinChannel(token, channel, "", uid)
    if ret != 0:
        print(f"[{label}] joinChannel failed code={ret}", file=sys.stderr)
        rtc.release()
        return

    time.sleep(duration)
    rtc.leaveChannel()
    time.sleep(2.0)
    rtc.release()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, default=None, help="Path to .env (default: repo/.env)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    env_path = args.env_file or (_repo_root() / ".env")
    load_dotenv(args.env_file)

    app_id = os.environ.get("AGORA_APP_ID", "").strip()
    if not app_id:
        print(
            "AGORA_APP_ID is missing or empty. Put your App ID from "
            "https://console.agora.io/ into `.env` as AGORA_APP_ID=... "
            "or run: export AGORA_APP_ID='your_app_id'",
            file=sys.stderr,
        )
        print(f"Expected `.env` at: {env_path.resolve()} (exists: {env_path.is_file()})", file=sys.stderr)
        if not env_path.is_file():
            print("Tip: cp .env.example .env   then edit AGORA_APP_ID.", file=sys.stderr)
        return 1

    token = os.environ.get("AGORA_TOKEN", "").strip()
    channel = os.environ.get("AGORA_CHANNEL", "demo-loadtest").strip()
    count = int(os.environ.get("CLIENT_COUNT", "100"))
    uid_start = int(os.environ.get("UID_START", "100001"))
    duration = float(os.environ.get("DURATION_SEC", "300"))
    role = os.environ.get("CLIENT_ROLE", "audience").strip().lower()
    stagger_ms = float(os.environ.get("JOIN_STAGGER_MS", "100"))
    target = int(os.environ.get("TARGET_CLIENT_COUNT", "10000"))

    raw_stats_idx = os.environ.get("RTC_STATS_LOG_CLIENT_INDEX", "0").strip().lower()
    if raw_stats_idx in ("", "none", "off", "-1"):
        stats_log_index: int | None = None
    else:
        stats_log_index = int(raw_stats_idx)

    if role not in ("audience", "broadcaster"):
        print("CLIENT_ROLE must be 'audience' or 'broadcaster'.", file=sys.stderr)
        return 1

    if count < 1:
        print("CLIENT_COUNT must be >= 1.", file=sys.stderr)
        return 1
    if count > 10000:
        print("CLIENT_COUNT capped at 10000.", file=sys.stderr)
        count = 10000
    if count > 500:
        print(
            f"Warning: spawning {count} processes is very heavy on CPU/RAM/network; "
            f"TARGET_CLIENT_COUNT={target} is usually reached with many machines, not one.",
            file=sys.stderr,
        )
    if count >= 2000:
        print(
            "Note: 2k+ full SDK processes on one machine is usually impractical (OOM, FD limits, "
            "thermal throttling). Use many machines or Agora’s official load-testing guidance.",
            file=sys.stderr,
        )

    raw_csv_dir = os.environ.get("RTC_STATS_CSV_DIR", "rtc_stats_logs").strip()
    if raw_csv_dir.lower() in ("none", "off", "0"):
        csv_dir: Path | None = None
    else:
        csv_dir = (_repo_root() / raw_csv_dir).resolve()
        csv_dir.mkdir(parents=True, exist_ok=True)

    repo_root = str(_repo_root())
    mp.set_start_method("spawn", force=True)

    processes: list[mp.Process] = []
    for i in range(count):
        uid = uid_start + i
        label = f"client-{i}-uid-{uid}"
        if csv_dir is not None:
            stats_csv_path = str(csv_dir / f"client_{i:05d}_uid_{uid}.csv")
        else:
            stats_csv_path = None
        cfg = {
            "repo_root": repo_root,
            "client_index": i,
            "uid": uid,
            "app_id": app_id,
            "token": token,
            "channel": channel,
            "duration_sec": duration,
            "role": role,
            "label": label,
            "log_periodic_rx": stats_log_index is not None and i == stats_log_index,
            "stats_csv_path": stats_csv_path,
        }
        proc = mp.Process(target=_worker, args=(cfg,))
        proc.start()
        processes.append(proc)
        time.sleep(stagger_ms / 1000.0)

    print(f"Started {len(processes)} workers; waiting for exit…")
    if csv_dir is not None:
        print(f"RTC stats CSV directory: {csv_dir}")
    for proc in processes:
        proc.join()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
