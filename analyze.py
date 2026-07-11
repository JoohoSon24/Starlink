#!/usr/bin/env python3
"""
analyze.py — 측정 결과 요약 (macOS/Linux 공통)

data/raw/static, data/raw/mobile 의 CSV를 읽어 파일(=지점/주행)별로
uptime, loss, RTT p50/p95/p99, spike 수를 요약한다.
단말 기록(data/raw/dish)이 있으면 같은 시간창의 평균 차폐율도 붙인다.

사용 예:
  python3 analysis/analyze.py --indir data/raw
출력:
  data/processed/summary.csv + 화면 표
"""

import argparse
from pathlib import Path

import pandas as pd

SPIKE_FACTOR = 3.0


def summarize_run(df: pd.DataFrame) -> dict:
    """1초 단위 ping 기록 하나(run)를 요약."""
    total = len(df)
    ok = df[df["success"] == 1]
    rtt = pd.to_numeric(ok["rtt_ms"], errors="coerce").dropna()
    out = {
        "samples": total,
        "uptime_pct": round(len(ok) / total * 100, 2) if total else None,
        "loss_pct": round((total - len(ok)) / total * 100, 2) if total else None,
    }
    if len(rtt):
        med = rtt.median()
        out.update({
            "rtt_p50": round(med, 1),
            "rtt_p95": round(rtt.quantile(0.95), 1),
            "rtt_p99": round(rtt.quantile(0.99), 1),
            "spikes": int((rtt > med * SPIKE_FACTOR).sum()),
        })
    return out


def attach_dish(summary: dict, run_df: pd.DataFrame, dish_dir: Path) -> dict:
    """run과 시간이 겹치는 dish 기록이 있으면 평균 차폐율/latency를 붙인다."""
    files = sorted(dish_dir.glob("*.csv"))
    if not files or "utc_time" not in run_df.columns or run_df.empty:
        return summary
    t0 = pd.to_datetime(run_df["utc_time"].iloc[0], utc=True)
    t1 = pd.to_datetime(run_df["utc_time"].iloc[-1], utc=True)
    frames = []
    for f in files:
        try:
            d = pd.read_csv(f)
            d["utc_time"] = pd.to_datetime(d["utc_time"], utc=True)
            frames.append(d[(d["utc_time"] >= t0) & (d["utc_time"] <= t1)])
        except Exception:
            continue
    if frames:
        dish = pd.concat(frames, ignore_index=True)
        if len(dish):
            summary["dish_obstruction_pct"] = round(
                dish["obstruction_fraction"].mean() * 100, 2)
            summary["dish_latency_ms"] = round(
                dish["pop_ping_latency_ms"].mean(), 1)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="data/raw")
    ap.add_argument("--out", default="data/processed/summary.csv")
    args = ap.parse_args()

    indir = Path(args.indir)
    dish_dir = indir / "dish"
    rows = []
    for sub in ["static", "mobile"]:
        for f in sorted((indir / sub).glob("*.csv")):
            if f.name.endswith("_events.csv"):
                continue
            try:
                df = pd.read_csv(f)
            except Exception as e:
                print(f"  (읽기 실패: {f.name}: {e})")
                continue
            if "success" not in df.columns:
                continue
            s = {"run": f.stem, "kind": sub, **summarize_run(df)}
            if dish_dir.exists():
                s = attach_dish(s, df, dish_dir)
            rows.append(s)

    if not rows:
        raise SystemExit(f"{indir} 아래에 분석할 CSV가 없습니다.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(rows)
    result.to_csv(out, index=False)
    print(result.to_string(index=False))
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
