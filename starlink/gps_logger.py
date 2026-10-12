#!/usr/bin/env python3
"""
gps_logger.py — macOS용 USB GPS 단독 테스트/로거

USB GPS(NMEA)를 백그라운드 스레드로 읽어 최신 위치를 유지하고,
1초 주기로 (시각, 위경도, 고도, 속도, 위성수)를 화면 출력 + CSV 저장.
measure_mobile.py 를 돌리기 전에 GPS 배선/포트가 정상인지 확인하는 용도.

포트 확인 (GPS 꽂은 뒤):
  ls /dev/cu.*
  # 예: /dev/cu.usbserial-1420, /dev/cu.usbmodem14201

사용 예:
  python3 gps_logger.py                          # 포트 자동 탐색
  python3 gps_logger.py --port /dev/cu.usbserial-1420
  python3 gps_logger.py --demo                   # GPS 없이 흐름 테스트

종료: Ctrl+C
"""

import argparse
import csv
import glob
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import serial
    import pynmea2
except ImportError:
    print("먼저 설치하세요:  pip install pyserial pynmea2")
    sys.exit(1)


def find_gps_port():
    """맥에서 그럴듯한 시리얼 포트를 자동 탐색. cu.* 를 우선한다."""
    candidates = (glob.glob("/dev/cu.usbserial*")
                  + glob.glob("/dev/cu.usbmodem*")
                  + glob.glob("/dev/cu.SLAB*")
                  + glob.glob("/dev/cu.wchusbserial*"))
    return candidates[0] if candidates else None


class GPSReader(threading.Thread):
    """백그라운드로 NMEA 문장을 읽어 최신 fix를 유지한다."""

    def __init__(self, port, baud=9600):
        super().__init__(daemon=True)
        self.ser = serial.Serial(port, baud, timeout=1)
        self.lock = threading.Lock()
        self.fix = {"lat": None, "lon": None, "alt": None,
                    "speed_kmh": None, "sats": None}
        self.running = True

    def run(self):
        while self.running:
            try:
                line = self.ser.readline().decode("ascii", errors="ignore").strip()
                if not line.startswith("$"):
                    continue
                msg = pynmea2.parse(line)
                stype = getattr(msg, "sentence_type", "")
                with self.lock:
                    if stype == "GGA" and msg.latitude:      # 위치·고도·위성수
                        self.fix["lat"] = msg.latitude
                        self.fix["lon"] = msg.longitude
                        self.fix["alt"] = float(msg.altitude) if msg.altitude else None
                        self.fix["sats"] = int(msg.num_sats or 0)
                    elif stype == "RMC" and msg.spd_over_grnd:  # 속도
                        self.fix["speed_kmh"] = float(msg.spd_over_grnd) * 1.852
            except (pynmea2.ParseError, UnicodeDecodeError):
                continue
            except Exception:
                continue

    def snapshot(self):
        with self.lock:
            return dict(self.fix)

    def stop(self):
        self.running = False
        try:
            self.ser.close()
        except Exception:
            pass


class DemoReader:
    """GPS 없이 테스트할 때 쓰는 가짜 리더. KAIST 좌표 근처를 움직인다."""

    def __init__(self):
        self._lat, self._lon = 36.3721, 127.3604

    def start(self):
        pass

    def snapshot(self):
        self._lat += 0.00001
        self._lon += 0.00001
        return {"lat": round(self._lat, 6), "lon": round(self._lon, 6),
                "alt": 70.0, "speed_kmh": 15.0, "sats": 9}

    def stop(self):
        pass


def main():
    ap = argparse.ArgumentParser(description="macOS USB GPS 로거")
    ap.add_argument("--port", default=None,
                    help="시리얼 포트 (생략 시 /dev/cu.* 자동 탐색)")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--interval", type=float, default=1.0, help="기록 주기(초)")
    ap.add_argument("--out", default=None, help="CSV 경로 (생략 시 자동 생성)")
    ap.add_argument("--demo", action="store_true", help="GPS 없이 가짜 데이터")
    args = ap.parse_args()

    if args.demo:
        reader = DemoReader()
        print("[demo] 가짜 GPS 데이터로 실행합니다.")
    else:
        port = args.port or find_gps_port()
        if not port:
            print("GPS 포트를 못 찾았습니다.  ls /dev/cu.*  로 확인 후 --port 지정.")
            print("또는 --demo 로 흐름만 테스트할 수 있습니다.")
            sys.exit(1)
        print(f"[gps] 포트 열기: {port} @ {args.baud}")
        try:
            reader = GPSReader(port, args.baud)
        except serial.SerialException as e:
            print(f"포트를 열 수 없습니다: {e}")
            sys.exit(1)

    reader.start()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out) if args.out else Path(f"gps_log_{stamp}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[csv] 저장: {out_path}")
    print("[run] 기록 시작. 종료: Ctrl+C\n")

    fields = ["utc_time", "lat", "lon", "alt", "speed_kmh", "sats"]
    fix_count = 0
    try:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            while True:
                t0 = time.time()
                snap = reader.snapshot()
                row = {"utc_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       **{k: snap[k] for k in ["lat", "lon", "alt", "speed_kmh", "sats"]}}
                writer.writerow(row)
                f.flush()
                if snap["lat"] is not None:
                    fix_count += 1
                    print(f"  {row['utc_time']}  lat={snap['lat']:.6f} lon={snap['lon']:.6f} "
                          f"alt={snap['alt']} spd={snap['speed_kmh']} sats={snap['sats']}")
                else:
                    print("  (위성 신호 대기 중... 실내면 창가/야외로)")
                time.sleep(max(0, args.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        print(f"\n[stop] 종료. 총 {fix_count}개 fix → {out_path}")
    finally:
        reader.stop()


if __name__ == "__main__":
    main()
