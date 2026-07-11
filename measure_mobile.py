#!/usr/bin/env python3
"""
measure_mobile.py — 동적(모빌리티) 측정 (macOS)

자전거 플랫폼: 맥북 + Starlink Mini + USB GPS(NMEA).
1초 주기로 (GPS 좌표, RTT)를 한 행으로 기록 → 이후 히트맵 생성에 사용.
단말 텔레메트리는 starlink_reader.py --log 를 병행 실행해서 따로 기록
(주기가 달라서 한 파일로 합치지 않는다 — 분석 단계에서 시간 정합).

사용 예:
  caffeinate -i python3 measure_mobile.py --route dorm-loop
  # GPS 포트 자동 탐색. 명시: --gps-port /dev/cu.usbserial-1420
  # GPS 없이 흐름 테스트: --demo

출력:
  data/raw/mobile/{route}_{timestamp}.csv
    utc_time, lat, lon, speed_kmh, num_sats, rtt_ms, success

종료: Ctrl+C
"""

import argparse
import csv
import glob
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import pynmea2
    import serial
except ImportError:
    print("먼저 설치하세요:  pip install pyserial pynmea2")
    sys.exit(1)

PING_TARGET = "8.8.8.8"


def find_gps_port():
    """맥 시리얼 포트 자동 탐색 (cu.* 우선)."""
    candidates = (glob.glob("/dev/cu.usbserial*")
                  + glob.glob("/dev/cu.usbmodem*")
                  + glob.glob("/dev/cu.SLAB*")
                  + glob.glob("/dev/cu.wchusbserial*"))
    return candidates[0] if candidates else None


class GPSReader(threading.Thread):
    """백그라운드로 NMEA 문장을 읽어 최신 fix를 유지."""

    def __init__(self, port: str, baud: int = 9600):
        super().__init__(daemon=True)
        self.ser = serial.Serial(port, baud, timeout=1)
        self.lock = threading.Lock()
        self.fix = {"lat": None, "lon": None, "speed_kmh": None, "sats": None}

    def run(self):
        while True:
            try:
                line = self.ser.readline().decode("ascii", errors="ignore").strip()
                if not line.startswith("$"):
                    continue
                msg = pynmea2.parse(line)
                with self.lock:
                    if msg.sentence_type == "GGA" and msg.latitude:
                        self.fix["lat"] = msg.latitude
                        self.fix["lon"] = msg.longitude
                        self.fix["sats"] = int(msg.num_sats or 0)
                    elif msg.sentence_type == "RMC" and msg.spd_over_grnd:
                        self.fix["speed_kmh"] = float(msg.spd_over_grnd) * 1.852
            except Exception:
                continue

    def snapshot(self):
        with self.lock:
            return dict(self.fix)


class DemoGPS:
    """GPS 없이 흐름 테스트용. KAIST 근처를 천천히 이동."""

    def __init__(self):
        self._lat, self._lon = 36.3721, 127.3604

    def start(self):
        pass

    def snapshot(self):
        self._lat += 0.00002
        self._lon += 0.00002
        return {"lat": round(self._lat, 6), "lon": round(self._lon, 6),
                "speed_kmh": 15.0, "sats": 9}


def ping_cmd(target: str, timeout_s: float):
    """OS별 1회 ping 명령. macOS는 -W가 밀리초."""
    if platform.system() == "Darwin":
        return ["ping", "-c", "1", "-W", str(int(timeout_s * 1000)), target]
    return ["ping", "-c", "1", "-W", str(int(timeout_s)), target]


def ping_once(target: str = PING_TARGET, timeout_s: float = 2.0):
    try:
        out = subprocess.run(ping_cmd(target, timeout_s),
                             capture_output=True, text=True,
                             timeout=timeout_s + 1)
        m = re.search(r"time=([\d.]+)", out.stdout)
        if out.returncode == 0 and m:
            return True, float(m.group(1))
    except Exception:
        pass
    return False, None


def main():
    ap = argparse.ArgumentParser(description="이동 측정: GPS + 1초 ping")
    ap.add_argument("--route", required=True, help="경로 라벨, 예: dorm-loop")
    ap.add_argument("--gps-port", default=None,
                    help="GPS 시리얼 포트 (생략 시 /dev/cu.* 자동 탐색)")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--target", default=PING_TARGET)
    ap.add_argument("--outdir", default="data/raw/mobile")
    ap.add_argument("--demo", action="store_true", help="GPS 없이 흐름 테스트")
    args = ap.parse_args()

    if args.demo:
        gps = DemoGPS()
        print("[demo] 가짜 GPS로 실행")
    else:
        port = args.gps_port or find_gps_port()
        if not port:
            print("GPS 포트를 못 찾았습니다.  ls /dev/cu.*  확인 후 --gps-port 지정,")
            print("또는 --demo 로 흐름 테스트.")
            sys.exit(1)
        print(f"[gps] {port} @ {args.baud}")
        gps = GPSReader(port, args.baud)
    gps.start()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{args.route}_{stamp}.csv"
    print(f"[csv] {out}")
    print("[run] 종료: Ctrl+C   (단말 기록은 starlink_reader.py --log 병행)\n")

    n = n_fix = n_fail = 0
    try:
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["utc_time", "lat", "lon", "speed_kmh",
                        "num_sats", "rtt_ms", "success"])
            while True:
                t0 = time.time()
                ok, rtt = ping_once(args.target)
                fix = gps.snapshot()
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                w.writerow([now, fix["lat"], fix["lon"], fix["speed_kmh"],
                            fix["sats"], rtt if rtt is not None else "", int(ok)])
                f.flush()

                n += 1
                if fix["lat"] is not None:
                    n_fix += 1
                if not ok:
                    n_fail += 1

                status = f"rtt={rtt}ms" if ok else "PING FAIL"
                loc = (f"({fix['lat']:.5f},{fix['lon']:.5f})"
                       if fix["lat"] is not None else "(no GPS fix)")
                print(f"  {now}  {loc}  {status}")

                time.sleep(max(0, 1.0 - (time.time() - t0)))
    except KeyboardInterrupt:
        print(f"\n[stop] 샘플 {n}  GPS fix {n_fix}  ping 실패 {n_fail} → {out}")


if __name__ == "__main__":
    main()
