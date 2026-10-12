#!/usr/bin/env python3
"""
plot_metrics.py — live_monitor.py가 저장한 CSV를 그래프로 보여준다 (macOS/Linux 공통)

3단 그래프(위→아래로 latency / throughput / loss·obstruction)를 하나의
PNG로 저장하고, 화면에도 띄운다. 요약 통계(평균/중앙값/p95/p99, 평균
throughput 등)는 콘솔에 함께 출력한다.

사용 예:
  # 가장 최근 live_monitor.py 결과를 자동으로 찾아 정적 그래프 1장 생성
  python3 plot_metrics.py

  # 특정 파일 지정
  python3 plot_metrics.py data/raw/live/balcony_20260805_141500.csv

  # live_monitor.py가 아직 돌아가는 동안 실시간으로 갱신되는 그래프 보기
  python3 plot_metrics.py --live
  python3 plot_metrics.py data/raw/live/balcony_20260805_141500.csv --live

출력:
  data/processed/plots/{csv 파일명}.png   (--live 모드에서는 저장하지 않고 창만 갱신)
"""

import argparse
import sys
import time
from pathlib import Path

try:
    import matplotlib
    import pandas as pd
except ImportError:
    print("먼저 설치하세요:  pip install matplotlib pandas")
    sys.exit(1)

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

ROLLING_WINDOW = 10  # 손실률 이동평균 창(샘플 수)


def find_latest_csv(indir: str) -> Path:
    files = sorted(Path(indir).glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(
            f"{indir} 에 CSV가 없습니다. 먼저 live_monitor.py로 측정을 저장하거나, "
            "--csv 로 파일 경로를 직접 지정하세요."
        )
    return files[-1]


def load(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if df.empty:
        return df
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True)
    df["ping_rtt_ms"] = pd.to_numeric(df.get("ping_rtt_ms"), errors="coerce")
    df["dish_pop_latency_ms"] = pd.to_numeric(df.get("dish_pop_latency_ms"), errors="coerce")
    df["downlink_mbps"] = pd.to_numeric(df.get("downlink_mbps"), errors="coerce")
    df["uplink_mbps"] = pd.to_numeric(df.get("uplink_mbps"), errors="coerce")
    df["obstruction_pct"] = pd.to_numeric(df.get("obstruction_fraction"), errors="coerce") * 100
    df["dish_loss_pct"] = pd.to_numeric(df.get("dish_drop_rate"), errors="coerce") * 100
    df["ping_loss_pct"] = (1 - df["ping_success"]) * 100
    df["ping_loss_roll_pct"] = (
        df["ping_loss_pct"].rolling(ROLLING_WINDOW, min_periods=1).mean()
    )
    return df


def print_summary(df: pd.DataFrame, csv_path: Path):
    print(f"\n[summary] {csv_path}")
    print(f"  샘플 수         : {len(df)}")
    site = df["site"].iloc[0] if "site" in df.columns and len(df) else "?"
    lat = df["lat"].iloc[0] if "lat" in df.columns and len(df) else None
    lon = df["lon"].iloc[0] if "lon" in df.columns and len(df) else None
    print(f"  위치            : {site}  (lat={lat}, lon={lon})")

    rtt = df["ping_rtt_ms"].dropna()
    if len(rtt):
        print(f"  ping RTT p50/p95/p99 : "
              f"{rtt.median():.1f} / {rtt.quantile(0.95):.1f} / {rtt.quantile(0.99):.1f} ms")
    print(f"  ping loss       : {df['ping_loss_pct'].mean():.2f}%")

    dl = df["downlink_mbps"].dropna()
    ul = df["uplink_mbps"].dropna()
    if len(dl):
        print(f"  downlink 평균/최대 : {dl.mean():.1f} / {dl.max():.1f} Mbps")
    if len(ul):
        print(f"  uplink 평균/최대   : {ul.mean():.1f} / {ul.max():.1f} Mbps")

    obst = df["obstruction_pct"].dropna()
    if len(obst):
        print(f"  obstruction 평균  : {obst.mean():.3f}%")


def draw(fig, axes, df: pd.DataFrame, title: str):
    for ax in axes:
        ax.clear()

    ax_lat, ax_thr, ax_loss = axes
    t = df["utc_time"]

    ax_lat.plot(t, df["ping_rtt_ms"], label="ping RTT (8.8.8.8)", color="#1f77b4", linewidth=1)
    if df["dish_pop_latency_ms"].notna().any():
        ax_lat.plot(t, df["dish_pop_latency_ms"], label="dish latency", color="#ff7f0e", linewidth=1)
    ax_lat.set_ylabel("latency (ms)")
    ax_lat.legend(loc="upper right", fontsize=8)
    ax_lat.set_title(title)

    ax_thr.plot(t, df["downlink_mbps"], label="downlink", color="#2ca02c", linewidth=1)
    ax_thr.plot(t, df["uplink_mbps"], label="uplink", color="#d62728", linewidth=1)
    ax_thr.set_ylabel("throughput (Mbps)")
    ax_thr.legend(loc="upper right", fontsize=8)

    ax_loss.plot(t, df["ping_loss_roll_pct"], label=f"ping loss (rolling {ROLLING_WINDOW})",
                 color="#1f77b4", linewidth=1)
    if df["obstruction_pct"].notna().any():
        ax_loss.plot(t, df["obstruction_pct"], label="obstruction", color="#9467bd", linewidth=1)
    ax_loss.set_ylabel("%")
    ax_loss.set_xlabel("UTC time")
    ax_loss.legend(loc="upper right", fontsize=8)

    fig.autofmt_xdate()


def run_static(csv_path: Path, outdir: Path):
    df = load(csv_path)
    if df.empty:
        raise SystemExit(f"{csv_path} 에 데이터가 없습니다.")
    print_summary(df, csv_path)

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    draw(fig, axes, df, f"Starlink live metrics — {csv_path.stem}")
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    out_png = outdir / f"{csv_path.stem}.png"
    fig.savefig(out_png, dpi=150)
    print(f"\n[png] 저장: {out_png}")
    plt.show()


def run_live(csv_path: Path, interval: float):
    print(f"[live] {csv_path} 를 실시간으로 지켜봅니다 (live_monitor.py가 계속 기록 중이어야 함).")
    print("[live] 창을 닫으면 종료.")

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

    def update(_frame):
        if not csv_path.exists():
            return
        try:
            df = load(csv_path)
        except Exception:
            return
        if df.empty:
            return
        draw(fig, axes, df, f"Starlink live metrics — {csv_path.stem} (live)")
        fig.tight_layout()

    ani = FuncAnimation(fig, update, interval=interval * 1000, cache_frame_data=False)
    plt.show()
    return ani


def main():
    ap = argparse.ArgumentParser(description="live_monitor.py CSV → 그래프")
    ap.add_argument("csv", nargs="?", default=None,
                     help="CSV 경로 (생략 시 --indir 안에서 가장 최근 파일 자동 선택)")
    ap.add_argument("--indir", default="data/raw/live", help="csv 생략 시 탐색할 폴더")
    ap.add_argument("--outdir", default="data/processed/plots", help="PNG 저장 폴더")
    ap.add_argument("--live", action="store_true",
                     help="실행 중인 live_monitor.py의 CSV를 실시간으로 갱신하며 표시")
    ap.add_argument("--interval", type=float, default=2.0, help="--live 갱신 주기(초, 기본 2)")
    args = ap.parse_args()

    csv_path = Path(args.csv) if args.csv else find_latest_csv(args.indir)
    if not csv_path.exists():
        raise SystemExit(f"파일이 없습니다: {csv_path}")

    if args.live:
        ani = run_live(csv_path, args.interval)  # noqa: F841 (참조 유지 — GC로 애니메이션 멈추는 것 방지)
    else:
        run_static(csv_path, Path(args.outdir))


if __name__ == "__main__":
    main()
