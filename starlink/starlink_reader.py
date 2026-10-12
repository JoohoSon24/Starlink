#!/usr/bin/env python3
"""
starlink_reader.py — Starlink 단말 텔레메트리 리더 (macOS/Linux 공통)

단말 로컬 gRPC API(192.168.100.1:9200)의 dish_get_status를 읽어
latency, throughput, obstruction(차폐율)을 가져온다.
gRPC 리플렉션(yagrc)을 쓰므로 .proto 컴파일이 필요 없다.

전제: 이 컴퓨터가 Starlink 네트워크(와이파이/이더넷)에 연결되어 있어야 함.
      먼저  ping 192.168.100.1  이 되는지 확인.

사용 예:
  python3 starlink_reader.py                       # 1회 출력
  python3 starlink_reader.py --watch               # 1초마다 계속 출력
  python3 starlink_reader.py --log --label N1-window-open
      # data/raw/dish/N1-window-open_{timestamp}.csv 에 1 Hz 기록
      # (measure_static.py / measure_mobile.py 와 병행 실행하는 용도)

종료: Ctrl+C
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import grpc
    from yagrc import reflector as yagrc_reflector
except ImportError:
    print("먼저 설치하세요:  pip install grpcio grpcio-tools yagrc")
    sys.exit(1)

DISH_ADDR = "192.168.100.1:9200"
FIELDS = ["utc_time", "state", "uptime_s", "pop_ping_latency_ms",
          "pop_ping_drop_rate", "downlink_mbps", "uplink_mbps",
          "obstruction_fraction", "obstruction_valid_s", "snr"]


def make_stub(channel):
    """gRPC 리플렉션으로 Device 서비스 스텁을 런타임 생성."""
    reflector = yagrc_reflector.GrpcReflectionClient()
    reflector.load_protocols(channel, symbols=["SpaceX.API.Device.Device"])
    request_cls = reflector.message_class("SpaceX.API.Device.Request")
    stub_cls = reflector.service_stub_class("SpaceX.API.Device.Device")
    return stub_cls(channel), request_cls


def get_status(stub, Request, timeout=5.0):
    """dish_get_status 1회 호출 → 주요 지표 dict."""
    response = stub.Handle(Request(get_status={}), timeout=timeout)
    s = response.dish_get_status
    ob = s.obstruction_stats
    return {
        "utc_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state": getattr(s, "state", None),
        "uptime_s": s.device_state.uptime_s if s.HasField("device_state") else None,
        "pop_ping_latency_ms": round(s.pop_ping_latency_ms, 1),
        "pop_ping_drop_rate": round(s.pop_ping_drop_rate, 4),
        "downlink_mbps": round(s.downlink_throughput_bps / 1e6, 2),
        "uplink_mbps": round(s.uplink_throughput_bps / 1e6, 2),
        "obstruction_fraction": round(ob.fraction_obstructed, 4),
        "obstruction_valid_s": round(ob.valid_s, 1),
        "snr": getattr(s, "snr", None),  # 구버전 펌웨어에서만 값 존재
    }


def print_status(st):
    print(f"  {st['utc_time']}")
    print(f"    latency    : {st['pop_ping_latency_ms']} ms  "
          f"(drop {st['pop_ping_drop_rate'] * 100:.2f}%)")
    print(f"    throughput : ↓{st['downlink_mbps']} / ↑{st['uplink_mbps']} Mbps")
    print(f"    obstruction: {st['obstruction_fraction'] * 100:.2f}%  "
          f"(측정 {st['obstruction_valid_s']}s)\n")


def main():
    ap = argparse.ArgumentParser(description="Starlink 단말 텔레메트리 리더")
    ap.add_argument("--watch", action="store_true", help="주기적으로 계속 출력")
    ap.add_argument("--log", action="store_true", help="CSV로 계속 기록")
    ap.add_argument("--label", default="dish", help="--log 시 파일명 라벨")
    ap.add_argument("--outdir", default="data/raw/dish", help="--log 저장 폴더")
    ap.add_argument("--interval", type=float, default=1.0, help="주기(초)")
    args = ap.parse_args()

    channel = grpc.insecure_channel(DISH_ADDR)
    try:
        stub, Request = make_stub(channel)
    except grpc.RpcError as e:
        print(f"단말에 연결할 수 없습니다: {e.code()}")
        print("이 컴퓨터가 Starlink 네트워크에 연결됐는지,")
        print("ping 192.168.100.1 이 되는지 먼저 확인하세요.")
        sys.exit(1)

    # 단발 조회
    if not (args.watch or args.log):
        print_status(get_status(stub, Request))
        return

    # 연속 모드 (watch / log)
    writer, fh = None, None
    if args.log:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(args.outdir) / f"{args.label}_{stamp}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        fh = open(out, "w", newline="")
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        print(f"[csv] 저장: {out}")

    print("[run] 종료: Ctrl+C\n")
    try:
        while True:
            t0 = time.time()
            try:
                st = get_status(stub, Request)
                if writer:
                    writer.writerow(st)
                    fh.flush()
                if args.watch or not args.log:
                    print_status(st)
                else:
                    print(f"  {st['utc_time']}  rtt={st['pop_ping_latency_ms']}ms  "
                          f"obst={st['obstruction_fraction'] * 100:.2f}%")
            except grpc.RpcError as e:
                print(f"  (단말 응답 없음: {e.code()})")
            time.sleep(max(0, args.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        print("\n[stop] 종료")
    finally:
        if fh:
            fh.close()
        channel.close()


if __name__ == "__main__":
    main()
