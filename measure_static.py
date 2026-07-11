#!/usr/bin/env python3
"""
measure_static.py — 정적 측정 (macOS)

한 지점(설치환경 라벨)에서 1초 주기 ping으로 RTT/loss를 기록하고,
spike(급등)와 outage(연속 실패) 이벤트를 별도 파일로 남긴다.
시작 시 traceroute 1회 저장. throughput(iperf3)은 시간대를 분리해
별도로 돌릴 것 (README 참고 — iperf가 RTT를 오염시키므로).

macOS 참고: ping -W 단위가 리눅스(초)와 달리 밀리초라서
platform 분기 처리함. 장시간 측정은 caffeinate로 잠자기 방지:
  caffeinate -i python3 measure_static.py --site N1-window-open --duration 3600

출력:
  data/raw/static/{site}_{timestamp}.csv          # 1초 단위 rtt
  data/raw/static/{site}_{timestamp}_events.csv   # spike / outage
  data/raw/static/{site}_{timestamp}_trace.txt    # traceroute
"""

import argparse
import csv
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

PING_TARGET = "8.8.8.8"
SPIKE_FACTOR = 3.0        # 이동평균 대비 몇 배면 spike로 볼지
OUTAGE_MIN_FAILS = 3      # 연속 몇 회 실패부터 outage로 볼지


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
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return False, None


def save_traceroute(target: str, path: Path):
    try:
        out = subprocess.run(["traceroute", "-m", "20", target],
                             capture_output=True, text=True, timeout=90)
        path.write_text(out.stdout)
        print(f"[trace] 저장: {path}")
    except Exception as e:
        print(f"[trace] 실패 (계속 진행): {e}")


def main():
    ap = argparse.ArgumentParser(description="정적 측정 (1초 ping + 이벤트)")
    ap.add_argument("--site", required=True,
                    help="지점-환경 라벨, 예: N1-window-open")
    ap.add_argument("--duration", type=int, default=3600, help="측정 시간(초)")
    ap.add_argument("--target", default=PING_TARGET)
    ap.add_argument("--outdir", default="data/raw/static")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / f"{args.site}_{stamp}"
    csv_path = Path(f"{base}.csv")
    ev_path = Path(f"{base}_events.csv")

    save_traceroute(args.target, Path(f"{base}_trace.txt"))

    print(f"[run] site={args.site}  duration={args.duration}s  target={args.target}")
    print(f"[csv] {csv_path}")

    ema = None            # RTT 지수이동평균 (spike 기준선)
    fail_streak = 0
    outage_start = None
    n_ok = n_fail = n_spike = 0

    with open(csv_path, "w", newline="") as f, open(ev_path, "w", newline="") as ef:
        w = csv.writer(f)
        w.writerow(["utc_time", "success", "rtt_ms"])
        ew = csv.writer(ef)
        ew.writerow(["utc_time", "event", "detail"])

        t_end = time.time() + args.duration
        while time.time() < t_end:
            t0 = time.time()
            ok, rtt = ping_once(args.target)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            w.writerow([now, int(ok), rtt if rtt is not None else ""])
            f.flush()

            if ok:
                n_ok += 1
                # outage 종료 처리
                if fail_streak >= OUTAGE_MIN_FAILS:
                    ew.writerow([now, "outage_end", f"lasted={fail_streak}s"])
                    ef.flush()
                fail_streak = 0
                # spike 판정
                if ema is not None and rtt > ema * SPIKE_FACTOR:
                    n_spike += 1
                    ew.writerow([now, "rtt_spike", f"rtt={rtt} ema={ema:.1f}"])
                    ef.flush()
                    print(f"  {now}  SPIKE rtt={rtt}ms (ema {ema:.1f})")
                ema = rtt if ema is None else 0.9 * ema + 0.1 * rtt
            else:
                n_fail += 1
                fail_streak += 1
                if fail_streak == OUTAGE_MIN_FAILS:
                    outage_start = now
                    ew.writerow([now, "outage_start", ""])
                    ef.flush()
                    print(f"  {now}  OUTAGE 시작")

            if (n_ok + n_fail) % 30 == 0:
                loss = n_fail / max(1, n_ok + n_fail) * 100
                print(f"  {now}  n={n_ok + n_fail}  loss={loss:.1f}%  "
                      f"ema={ema:.1f}ms  spikes={n_spike}" if ema else
                      f"  {now}  n={n_ok + n_fail}  loss={loss:.1f}%")

            time.sleep(max(0, 1.0 - (time.time() - t0)))

    total = n_ok + n_fail
    print(f"\n[done] 샘플 {total}  loss={n_fail / max(1, total) * 100:.2f}%  "
          f"spike={n_spike}")
    print("throughput은 별도로:")
    print(f"  iperf3 -c <서버IP> -t 60 -J     > {base}_iperf_up.json")
    print(f"  iperf3 -c <서버IP> -t 60 -J -R  > {base}_iperf_down.json")


if __name__ == "__main__":
    main()
