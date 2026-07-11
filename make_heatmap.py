#!/usr/bin/env python3
"""
make_heatmap.py — 이동 측정 결과 → 히트맵 HTML (macOS/Linux 공통)

data/raw/mobile 의 CSV들을 합쳐 folium 지도로 만든다.
결과 HTML은 GitHub Pages로 그대로 배포 가능.

사용 예:
  python3 analysis/make_heatmap.py --indir data/raw/mobile --out web/heatmap.html
  open web/heatmap.html        # (macOS) 브라우저로 바로 열기

레이어:
  1) RTT 히트맵 (RTT가 클수록 진하게 → 문제 지역이 눈에 띄도록)
  2) 끊김(ping 실패) 지점 마커
"""

import argparse
from pathlib import Path

import folium
import pandas as pd
from folium.plugins import HeatMap

KAIST_CENTER = (36.3721, 127.3604)  # KAIST 본원 대략 중심


def load_all(indir: str) -> pd.DataFrame:
    files = sorted(Path(indir).glob("*.csv"))
    if not files:
        raise SystemExit(f"{indir} 에 CSV가 없습니다.")
    df = pd.concat((pd.read_csv(f).assign(route=f.stem) for f in files),
                   ignore_index=True)
    return df.dropna(subset=["lat", "lon"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="data/raw/mobile")
    ap.add_argument("--out", default="web/heatmap.html")
    args = ap.parse_args()

    df = load_all(args.indir)
    ok = df[df["success"] == 1].copy()
    fail = df[df["success"] == 0]

    m = folium.Map(location=KAIST_CENTER, zoom_start=16,
                   tiles="cartodbpositron")

    # RTT 히트맵
    if len(ok):
        ok["rtt_ms"] = pd.to_numeric(ok["rtt_ms"], errors="coerce")
        ok = ok.dropna(subset=["rtt_ms"])
        rtt_cap = ok["rtt_ms"].quantile(0.99)
        heat = [[r.lat, r.lon, min(r.rtt_ms, rtt_cap) / rtt_cap]
                for r in ok.itertuples()]
        HeatMap(heat, radius=12, blur=18, name="RTT heatmap").add_to(m)

    # 끊김 지점 마커
    fg = folium.FeatureGroup(name="Connection drops")
    for r in fail.itertuples():
        folium.CircleMarker(
            location=(r.lat, r.lon), radius=4, color="red", fill=True,
            popup=f"{r.route}<br>{r.utc_time}",
        ).add_to(fg)
    fg.add_to(m)

    folium.LayerControl().add_to(m)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    print(f"지도 저장 완료: {out}  (샘플 {len(df)}개, 끊김 {len(fail)}개)")


if __name__ == "__main__":
    main()
