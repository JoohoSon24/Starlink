#!/usr/bin/env python3
"""
load_test.py — 다중 사용자 부하 실험 (macOS/Linux 공통)

iperf3 클라이언트를 1/2/4/8개 동시에 띄워 인당 throughput이
어떻게 나뉘는지 측정한다. 서버 쪽에는 클라이언트 수만큼
포트를 열어둘 것 (5201, 5202, ...):
  iperf3 -s -p 5201 &   iperf3 -s -p 5202 &  ...

사용 예:
  caffeinate -i python3 load_test.py --server <서버IP> --clients 1 2 4 8 --duration 60

출력:
  data/raw/load/load_c{N}_{timestamp}_p{port}.json  (클라이언트별 iperf3 JSON)
  화면에 조건별 합계/인당 평균 요약
"""

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

BASE_PORT = 5201


def run_condition(server: str, n_clients: int, duration: int,
                  outdir: Path, reverse: bool):
    """클라이언트 n개를 동시에 실행하고 JSON 결과를 저장."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    procs, paths = [], []
    for i in range(n_clients):
        port = BASE_PORT + i
        path = outdir / f"load_c{n_clients}_{stamp}_p{port}.json"
        cmd = ["iperf3", "-c", server, "-p", str(port),
               "-t", str(duration), "-J"]
        if reverse:
            cmd.append("-R")
        procs.append((subprocess.Popen(cmd, stdout=open(path, "w"),
                                       stderr=subprocess.DEVNULL), path))
        paths.append(path)
    for p, _ in procs:
        p.wait()

    # 결과 집계
    total_mbps, ok = 0.0, 0
    for path in paths:
        try:
            data = json.loads(path.read_text())
            bps = data["end"]["sum_received" if reverse else "sum_sent"]["bits_per_second"]
            total_mbps += bps / 1e6
            ok += 1
        except Exception:
            print(f"    (파싱 실패: {path.name} — 서버 포트가 열려있는지 확인)")
    return total_mbps, ok


def main():
    ap = argparse.ArgumentParser(description="iperf3 다중 세션 부하 실험")
    ap.add_argument("--server", required=True, help="iperf3 서버 IP")
    ap.add_argument("--clients", type=int, nargs="+", default=[1, 2, 4, 8],
                    help="동시 클라이언트 수 목록")
    ap.add_argument("--duration", type=int, default=60, help="조건당 시간(초)")
    ap.add_argument("--gap", type=int, default=30,
                    help="조건 사이 휴지(초) — 링크 안정화용")
    ap.add_argument("--reverse", action="store_true",
                    help="다운로드 방향(-R)으로 측정 (기본은 업로드)")
    ap.add_argument("--outdir", default="data/raw/load")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    direction = "download" if args.reverse else "upload"
    print(f"[run] server={args.server}  direction={direction}  "
          f"conditions={args.clients}\n")

    results = []
    for n in args.clients:
        print(f"  ▶ 동시 {n}개 클라이언트, {args.duration}s ...")
        total, ok = run_condition(args.server, n, args.duration,
                                  outdir, args.reverse)
        per = total / ok if ok else 0
        results.append((n, ok, total, per))
        print(f"    합계 {total:.1f} Mbps  /  인당 평균 {per:.1f} Mbps  "
              f"(성공 {ok}/{n})")
        if n != args.clients[-1]:
            time.sleep(args.gap)

    print("\n[summary]")
    print(f"  {'clients':>8} {'ok':>4} {'total Mbps':>12} {'per-client':>12}")
    for n, ok, total, per in results:
        print(f"  {n:>8} {ok:>4} {total:>12.1f} {per:>12.1f}")


if __name__ == "__main__":
    main()
