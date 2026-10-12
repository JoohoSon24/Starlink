# 집 와이파이 정적 측정

Starlink 없이, 지금 연결된 일반 와이파이(공유기)에서 같은 방식으로
1초 주기 ping 측정을 돌려보기 위한 코드. `../starlink/measure_static.py`와
달리 매초 게이트웨이(공유기)와 인터넷(기본 8.8.8.8) 두 구간을 같이 재서
어느 구간에서 지연/손실이 나는지 구분할 수 있게 했다.

## 실행

```bash
cd localwifi
python3 measure_static.py --site livingroom --duration 3600

# 장시간 측정 시 맥 잠자기 방지
caffeinate -i python3 measure_static.py --site livingroom --duration 3600
```

`--site`는 자리 라벨(예: `livingroom`, `desk-2m`). 게이트웨이 IP는 자동
탐색하며, 필요하면 `--gateway 192.168.0.1`처럼 직접 지정 가능.

## 출력 (`data/raw/` 아래)

- `{site}_{timestamp}.csv` — 1초 단위 `gw_rtt_ms` / `inet_rtt_ms`
- `{site}_{timestamp}_events.csv` — spike / outage (인터넷 구간 기준 판정)
- `{site}_{timestamp}_wifi.txt` — SSID 등 와이파이 정보
- `{site}_{timestamp}_trace.txt` — traceroute 1회

## 참고

- 외부 라이브러리 없이 표준 라이브러리 + macOS 내장 명령(`ping`,
  `traceroute`, `networksetup`, `route`, `ipconfig`)만 사용.
- throughput(iperf3)이 필요하면 ping 측정과 시간을 분리해서 별도로 돌릴 것
  (iperf3가 링크를 포화시켜 RTT를 오염시킴) — `../starlink/measure_static.py`
  하단 안내 참고.
