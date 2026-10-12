#!/usr/bin/env python3
"""
live_monitor.py — 고정 지점 실시간 네트워크 지표 모니터 (macOS/Linux 공통)

지금 이 컴퓨터가 연결된 Starlink Wi-Fi에서, 위치가 하나로 고정된 상태를
전제로 흔히 쓰는 네트워크 지표를 1초 주기로 화면에 계속 출력하면서
동시에 CSV로 저장한다. 두 종류의 지표를 합친다:

  1) 능동 측정 (ping)         — RTT, 손실률           (target: 8.8.8.8)
  2) 단말 자체 텔레메트리 (dish gRPC 192.168.100.1:9200)
                               — 단말 latency, drop rate,
                                 downlink/uplink throughput,
                                 obstruction(차폐율), SNR, 가동시간, 상태

측정/이동측정(measure_static.py, measure_mobile.py)과 달리 이 스크립트는
"위치 고정 + 실시간으로 보면서 기록"이 목적이라, 서로 다른 두 스트림을
같은 1 Hz 주기 안에서 한 행으로 합쳐 기록한다 (README '설계 원칙' 참고 —
iperf3처럼 링크를 포화시키는 측정은 여기 포함하지 않으므로 오염 문제가 없음).

위치는 GPS가 아니라 CLI 인자로 한 번 지정한 값을 모든 행에 그대로 채운다.
좌표를 모르면 --lat/--lon 없이 실행해도 되고(위치 칸은 빈 값), 알고 있으면
스마트폰 GPS 앱 등으로 한 번 확인해서 넘겨주면 된다.

단말(dish) gRPC 연결이 안 되더라도 프로그램을 죽이지 않고 ping 지표만
계속 기록한다 (starlink_reader.py는 실패 시 종료하지만, 이 스크립트는
"돌아가는 걸 계속 보는" 용도라 죽으면 안 됨). 재연결은 --dish-retry 주기로
자동 재시도한다.

사용 예:
  python3 live_monitor.py --site balcony --lat 36.3721 --lon 127.3604
  caffeinate -i python3 live_monitor.py --site balcony --lat 36.3721 --lon 127.3604 --duration 3600

출력:
  data/raw/live/{site}_{timestamp}.csv
    utc_time, site, lat, lon, ping_success, ping_rtt_ms,
    dish_state, dish_uptime_s, dish_pop_latency_ms, dish_drop_rate,
    downlink_mbps, uplink_mbps, obstruction_fraction, obstruction_valid_s, snr

  화면에는 매 초 한 줄씩 요약이 계속 출력되고(주루룩), 30줄마다 누적 통계도 출력.
  이 CSV를 그대로 plot_metrics.py에 넘기면 그래프를 볼 수 있다.

종료: Ctrl+C
"""

import argparse
import csv
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import grpc
    from yagrc import reflector as yagrc_reflector
except ImportError:
    grpc = None

PING_TARGET = "8.8.8.8"
DISH_ADDR = "192.168.100.1:9200"

FIELDS = [
    "utc_time", "site", "lat", "lon",
    "ping_success", "ping_rtt_ms",
    "dish_state", "dish_uptime_s", "dish_pop_latency_ms", "dish_drop_rate",
    "downlink_mbps", "uplink_mbps",
    "obstruction_fraction", "obstruction_valid_s", "snr",
]


# ---------- ping (measure_static.py와 동일 로직) ----------

def ping_cmd(target: str, timeout_s: float):
    """OS별 1회 ping 명령. macOS는 -W가 밀리초, 리눅스는 초."""
    if platform.system() == "Darwin":
        return ["ping", "-c", "1", "-W", str(int(timeout_s * 1000)), target]
    return ["ping", "-c", "1", "-W", str(int(timeout_s)), target]


def ping_once(target: str = PING_TARGET, timeout_s: float = 2.0):
    """1회 ping → (성공여부, rtt_ms)."""
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


# ---------- dish gRPC (starlink_reader.py와 동일 로직) ----------

class DishClient:
    """단말 gRPC 연결을 유지하고, 끊기면 조용히 재시도하는 래퍼."""

    def __init__(self, retry_interval: float):
        self.retry_interval = retry_interval
        self.channel = None
        self.stub = None
        self.Request = None
        self._last_attempt = 0.0
        self.available = False
        if grpc is None:
            print("[dish] grpcio/yagrc 미설치 — 단말 텔레메트리 없이 ping만 기록합니다.")
            print("       (설치하려면: pip install grpcio grpcio-tools yagrc)")
        else:
            self._connect(initial=True)

    def _connect(self, initial: bool = False):
        self._last_attempt = time.time()
        try:
            channel = grpc.insecure_channel(DISH_ADDR)
            reflector = yagrc_reflector.GrpcReflectionClient()
            reflector.load_protocols(channel, symbols=["SpaceX.API.Device.Device"])
            self.Request = reflector.message_class("SpaceX.API.Device.Request")
            stub_cls = reflector.service_stub_class("SpaceX.API.Device.Device")
            self.channel = channel
            self.stub = stub_cls(channel)
            self.available = True
            print("[dish] 단말 gRPC 연결 성공")
        except Exception as e:
            self.available = False
            if initial:
                print(f"[dish] 단말에 연결할 수 없습니다 ({e}).")
                print("       ping 지표만 기록하며, "
                      f"{self.retry_interval:.0f}초마다 재연결을 시도합니다.")
                print("       (Starlink Wi-Fi에 연결됐는지, ping 192.168.100.1 되는지 확인)")

    def get_status(self):
        """dish 상태 dict 반환. 실패하면 재연결 주기 확인 후 빈 dict."""
        empty = {k: None for k in FIELDS if k.startswith("dish_")
                  or k in ("downlink_mbps", "uplink_mbps",
                           "obstruction_fraction", "obstruction_valid_s", "snr")}
        if not self.available:
            if time.time() - self._last_attempt >= self.retry_interval:
                self._connect()
            return empty if not self.available else self.get_status()
        try:
            response = self.stub.Handle(self.Request(get_status={}), timeout=2.0)
            s = response.dish_get_status
            ob = s.obstruction_stats
            return {
                "dish_state": getattr(s, "state", None),
                "dish_uptime_s": s.device_state.uptime_s if s.HasField("device_state") else None,
                "dish_pop_latency_ms": round(s.pop_ping_latency_ms, 1),
                "dish_drop_rate": round(s.pop_ping_drop_rate, 4),
                "downlink_mbps": round(s.downlink_throughput_bps / 1e6, 2),
                "uplink_mbps": round(s.uplink_throughput_bps / 1e6, 2),
                "obstruction_fraction": round(ob.fraction_obstructed, 4),
                "obstruction_valid_s": round(ob.valid_s, 1),
                "snr": getattr(s, "snr", None),
            }
        except Exception:
            self.available = False
            print("[dish] 단말 응답 없음 — 재연결 대기")
            return empty


# ---------- 메인 루프 ----------

def format_line(row: dict) -> str:
    t = row["utc_time"].split("T")[1].split("+")[0]
    ping = f"{row['ping_rtt_ms']:.1f}ms" if row["ping_rtt_ms"] is not None else "FAIL"
    if row["dish_pop_latency_ms"] is not None:
        dish = (f"dish={row['dish_pop_latency_ms']}ms  "
                f"↓{row['downlink_mbps']}/↑{row['uplink_mbps']}Mbps  "
                f"loss={row['dish_drop_rate'] * 100:.2f}%  "
                f"obst={row['obstruction_fraction'] * 100:.2f}%")
    else:
        dish = "dish=n/a"
    return f"  {t}  ping={ping}  {dish}"


def main():
    ap = argparse.ArgumentParser(description="고정 지점 실시간 네트워크 지표 모니터 (출력 + CSV 저장)")
    ap.add_argument("--site", required=True, help="위치 라벨, 예: balcony, desk-window")
    ap.add_argument("--lat", type=float, default=None, help="고정 위도 (선택)")
    ap.add_argument("--lon", type=float, default=None, help="고정 경도 (선택)")
    ap.add_argument("--duration", type=int, default=0,
                     help="측정 시간(초). 0이면 Ctrl+C까지 무한 실행 (기본 0)")
    ap.add_argument("--target", default=PING_TARGET, help="ping 대상 (기본 8.8.8.8)")
    ap.add_argument("--interval", type=float, default=1.0, help="측정 주기(초, 기본 1)")
    ap.add_argument("--dish-retry", type=float, default=15.0,
                     help="단말 gRPC 재연결 시도 주기(초, 기본 15)")
    ap.add_argument("--outdir", default="data/raw/live")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / f"{args.site}_{stamp}.csv"

    dish = DishClient(args.dish_retry)

    print(f"[run] site={args.site}  lat={args.lat}  lon={args.lon}  "
          f"target={args.target}  interval={args.interval}s")
    print(f"[csv] {out_path}")
    print("[run] 종료: Ctrl+C   (그래프는 plot_metrics.py 참고)\n")

    n = n_ping_ok = n_ping_fail = n_dish_ok = 0
    rtt_sum = 0.0
    t_end = time.time() + args.duration if args.duration > 0 else None

    try:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            while t_end is None or time.time() < t_end:
                t0 = time.time()
                ok, rtt = ping_once(args.target)
                dish_status = dish.get_status()
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")

                row = {
                    "utc_time": now, "site": args.site,
                    "lat": args.lat, "lon": args.lon,
                    "ping_success": int(ok),
                    "ping_rtt_ms": rtt,
                    **dish_status,
                }
                writer.writerow(row)
                f.flush()

                n += 1
                if ok:
                    n_ping_ok += 1
                    rtt_sum += rtt
                else:
                    n_ping_fail += 1
                if dish_status.get("dish_pop_latency_ms") is not None:
                    n_dish_ok += 1

                print(format_line(row))
                if n % 30 == 0:
                    avg_rtt = rtt_sum / max(1, n_ping_ok)
                    loss = n_ping_fail / n * 100
                    print(f"  --- {n}개 샘플  평균 ping RTT={avg_rtt:.1f}ms  "
                          f"ping loss={loss:.1f}%  dish 응답 {n_dish_ok}/{n} ---")

                time.sleep(max(0, args.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        if dish.channel:
            dish.channel.close()

    avg_rtt = rtt_sum / max(1, n_ping_ok)
    print(f"\n[stop] 샘플 {n}  평균 ping RTT={avg_rtt:.1f}ms  "
          f"ping loss={n_ping_fail / max(1, n) * 100:.2f}%  "
          f"dish 응답 {n_dish_ok}/{n} → {out_path}")
    print(f"그래프로 보려면:  python3 plot_metrics.py {out_path}")


if __name__ == "__main__":
    main()
