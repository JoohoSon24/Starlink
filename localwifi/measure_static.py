#!/usr/bin/env python3
"""
measure_static.py — 집/사무실 와이파이 정적 측정 (macOS)

Starlink 버전(../starlink/measure_static.py)과 같은 방식으로 한 자리에서
1초 주기 ping을 돌리되, 매초 두 구간을 같이 잰다:
  1) 공유기(게이트웨이)까지 RTT  → 와이파이 구간만의 지연/손실
  2) 인터넷(기본 8.8.8.8)까지 RTT → 와이파이 + ISP 전체 지연/손실

게이트웨이는 낮고 안정적인데 인터넷 쪽만 튀면 ISP/외부 구간 문제,
둘 다 같이 튀면 우리 집 와이파이 자체(간섭, 신호 약함 등) 문제로
구분할 수 있다. spike/outage 이벤트는 인터넷 구간 기준으로 판정한다.

시작 시 SSID 등 와이파이 정보와 traceroute를 1회 저장한다.

사용:
  python3 measure_static.py --site livingroom --duration 3600
  caffeinate -i python3 measure_static.py --site livingroom --duration 3600  # 장시간

출력 (기본 outdir=data/raw):
  data/raw/{site}_{timestamp}.csv          # 1초 단위 gw/inet rtt
  data/raw/{site}_{timestamp}_events.csv   # spike / outage (인터넷 기준)
  data/raw/{site}_{timestamp}_wifi.txt     # SSID 등 와이파이 정보
  data/raw/{site}_{timestamp}_trace.txt    # traceroute
"""

import argparse
import csv
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

INET_TARGET = "8.8.8.8"
SPIKE_FACTOR = 3.0        # 이동평균 대비 몇 배면 spike로 볼지 (인터넷 구간 기준)
OUTAGE_MIN_FAILS = 3      # 연속 몇 회 실패부터 outage로 볼지 (인터넷 구간 기준)


def ping_cmd(target: str, timeout_s: float):
    """OS별 1회 ping 명령. macOS는 -W가 밀리초, 리눅스는 초."""
    if platform.system() == "Darwin":
        return ["ping", "-c", "1", "-W", str(int(timeout_s * 1000)), target]
    return ["ping", "-c", "1", "-W", str(int(timeout_s)), target]


def ping_once(target: str, timeout_s: float = 1.0):
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


def get_wifi_interface() -> str:
    """Wi-Fi 하드웨어 포트의 장치명(en0 등)을 찾는다. 실패하면 en0로 가정."""
    try:
        out = subprocess.run(["networksetup", "-listallhardwareports"],
                             capture_output=True, text=True, timeout=5).stdout
        blocks = out.split("Hardware Port: ")[1:]
        for b in blocks:
            if b.startswith("Wi-Fi") or b.startswith("AirPort"):
                m = re.search(r"Device:\s*(\S+)", b)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "en0"


def get_default_gateway():
    """기본 게이트웨이(공유기) IP를 찾는다."""
    try:
        out = subprocess.run(["route", "-n", "get", "default"],
                             capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"gateway:\s*(\S+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def save_wifi_info(iface: str, path: Path):
    lines = []
    try:
        ssid_out = subprocess.run(["networksetup", "-getairportnetwork", iface],
                                  capture_output=True, text=True, timeout=5).stdout
        lines.append(ssid_out.strip())
    except Exception as e:
        lines.append(f"SSID 조회 실패: {e}")
    try:
        info_out = subprocess.run(["ipconfig", "getsummary", iface],
                                  capture_output=True, text=True, timeout=5).stdout
        lines.append(info_out.strip())
    except Exception as e:
        lines.append(f"ipconfig 조회 실패: {e}")
    path.write_text("\n\n".join(lines) + "\n")
    print(f"[wifi] 저장: {path}")


def save_traceroute(target: str, path: Path):
    try:
        out = subprocess.run(["traceroute", "-m", "20", target],
                             capture_output=True, text=True, timeout=90)
        path.write_text(out.stdout)
        print(f"[trace] 저장: {path}")
    except Exception as e:
        print(f"[trace] 실패 (계속 진행): {e}")


def main():
    ap = argparse.ArgumentParser(description="집 와이파이 정적 측정 (1초 게이트웨이+인터넷 ping)")
    ap.add_argument("--site", required=True,
                    help="자리 라벨, 예: livingroom, desk-2m")
    ap.add_argument("--duration", type=int, default=3600, help="측정 시간(초)")
    ap.add_argument("--target", default=INET_TARGET, help="인터넷 측 ping 대상")
    ap.add_argument("--gateway", default=None,
                    help="공유기 IP (생략 시 자동 탐색)")
    ap.add_argument("--outdir", default="data/raw")
    args = ap.parse_args()

    iface = get_wifi_interface()
    gateway = args.gateway or get_default_gateway()
    if not gateway:
        print("[경고] 게이트웨이 IP를 자동으로 못 찾았습니다. --gateway로 직접 지정하세요.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / f"{args.site}_{stamp}"
    csv_path = Path(f"{base}.csv")
    ev_path = Path(f"{base}_events.csv")

    save_wifi_info(iface, Path(f"{base}_wifi.txt"))
    save_traceroute(args.target, Path(f"{base}_trace.txt"))

    print(f"[run] site={args.site}  duration={args.duration}s  "
          f"gateway={gateway}  target={args.target}")
    print(f"[csv] {csv_path}")

    ema = None            # 인터넷 RTT 지수이동평균 (spike 기준선)
    fail_streak = 0
    n_ok = n_fail = n_spike = 0
    n_gw_ok = n_gw_fail = 0

    with open(csv_path, "w", newline="") as f, open(ev_path, "w", newline="") as ef:
        w = csv.writer(f)
        w.writerow(["utc_time", "gw_success", "gw_rtt_ms", "inet_success", "inet_rtt_ms"])
        ew = csv.writer(ef)
        ew.writerow(["utc_time", "event", "detail"])

        t_end = time.time() + args.duration
        while time.time() < t_end:
            t0 = time.time()
            gw_ok, gw_rtt = ping_once(gateway)
            inet_ok, inet_rtt = ping_once(args.target)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            w.writerow([now, int(gw_ok), gw_rtt if gw_rtt is not None else "",
                       int(inet_ok), inet_rtt if inet_rtt is not None else ""])
            f.flush()

            if gw_ok:
                n_gw_ok += 1
            else:
                n_gw_fail += 1

            if inet_ok:
                n_ok += 1
                if fail_streak >= OUTAGE_MIN_FAILS:
                    ew.writerow([now, "outage_end", f"lasted={fail_streak}s"])
                    ef.flush()
                fail_streak = 0
                if ema is not None and inet_rtt > ema * SPIKE_FACTOR:
                    n_spike += 1
                    ew.writerow([now, "rtt_spike", f"rtt={inet_rtt} ema={ema:.1f}"])
                    ef.flush()
                    print(f"  {now}  SPIKE inet_rtt={inet_rtt}ms (ema {ema:.1f})")
                ema = inet_rtt if ema is None else 0.9 * ema + 0.1 * inet_rtt
            else:
                n_fail += 1
                fail_streak += 1
                if fail_streak == OUTAGE_MIN_FAILS:
                    ew.writerow([now, "outage_start", ""])
                    ef.flush()
                    print(f"  {now}  OUTAGE 시작 (인터넷 구간)")

            if (n_ok + n_fail) % 30 == 0:
                gw_loss = n_gw_fail / max(1, n_gw_ok + n_gw_fail) * 100
                inet_loss = n_fail / max(1, n_ok + n_fail) * 100
                ema_str = f"  ema={ema:.1f}ms" if ema else ""
                print(f"  {now}  n={n_ok + n_fail}  gw_loss={gw_loss:.1f}%  "
                      f"inet_loss={inet_loss:.1f}%{ema_str}  spikes={n_spike}")

            time.sleep(max(0, 1.0 - (time.time() - t0)))

    total = n_ok + n_fail
    gw_total = n_gw_ok + n_gw_fail
    print(f"\n[done] 샘플 {total}  "
          f"gw_loss={n_gw_fail / max(1, gw_total) * 100:.2f}%  "
          f"inet_loss={n_fail / max(1, total) * 100:.2f}%  spike={n_spike}")


if __name__ == "__main__":
    main()
