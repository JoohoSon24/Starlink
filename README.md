# KAIST 캠퍼스 Starlink Mini LEO 위성통신 실측 프로젝트 (macOS 버전)

맥북 + Starlink Mini + USB GPS(NMEA) 조합으로 캠퍼스 내
위성통신 성능(RTT / loss / throughput / 차폐율)을 실측하고
히트맵·공개 데이터셋을 만드는 프로젝트의 실행 코드.

리눅스 버전과의 차이는 맨 아래 "macOS 특이사항" 참고.

---

## 리포지터리 구조

```
starlink-kaist-mac/
├── README.md
├── requirements.txt
├── scripts/
│   ├── gps_logger.py        # USB GPS 단독 테스트/로깅 (포트 자동 탐색, --demo 지원)
│   ├── starlink_reader.py   # 단말 gRPC 텔레메트리 (1회 조회 / --watch / --log CSV)
│   ├── measure_static.py    # 정적 측정: 1초 ping, spike·끊김 이벤트, 시작 시 traceroute
│   ├── measure_mobile.py    # 이동 측정: GPS(NMEA) + 1초 ping 결합 로깅
│   └── load_test.py         # iperf3 다중 세션 부하 실험 (1/2/4/8 클라이언트)
├── analysis/
│   ├── analyze.py           # 지점별 요약: uptime, loss, p50/p95/p99, spike 수
│   └── make_heatmap.py      # folium 히트맵 → web/heatmap.html
├── data/
│   ├── raw/{static,mobile,load,dish}/
│   └── processed/
└── web/                     # GitHub Pages로 배포할 HTML
```

## 설계 원칙 (중요)

데이터 소스는 세 종류이고 **각자 주기가 다르다**:

| 스트림 | 소스 | 주기 |
|---|---|---|
| GPS 위치 | USB GPS → 시리얼 포트 | 1 Hz |
| 단말 텔레메트리 | Starlink dish gRPC `192.168.100.1:9200` | ~1 Hz |
| 능동 측정 | ping(RTT/loss) 1 Hz, iperf3(throughput)는 짧은 버스트 | 혼합 |

수집 시점에 한 줄로 억지로 합치지 않는다. 모든 행에 UTC 타임스탬프를
찍어 **스트림별로 따로 저장**하고, 분석 단계(`analysis/analyze.py`)에서
시간 기준으로 정합한다.

또 하나: **iperf3는 링크를 포화시키므로 돌리는 동안 RTT가 치솟는다.**
throughput과 latency는 같은 시간대에 측정하지 말 것.

---

## 설치

```bash
# 1. Python 패키지
pip install -r requirements.txt

# 2. 시스템 도구 (Homebrew)
brew install iperf3
# ping, traceroute는 macOS 기본 내장

# 3. (선택) USB 시리얼 드라이버 — GPS가 인식 안 될 때만
brew install --cask silicon-labs-vcp-driver   # CP210x 칩 계열
```

**iperf3 서버**: 유선망(연구실 PC 또는 클라우드 VM)에 `iperf3 -s -p 5201` 실행.
부하 실험용으로는 5201~5208 포트에 서버 인스턴스를 각각 띄워둘 것.

**시계 동기화**: 측정 전 반드시 확인 (스트림 정합의 전제).
```bash
sudo sntp -sS time.apple.com
# 또는 시스템 설정 > 일반 > 날짜와 시간 > 자동 설정 켜기
```

---

## 사전 점검 (측정 나가기 전에)

```bash
# USB GPS 인식 확인 — 꽂은 뒤 새로 생긴 cu.* 가 GPS
ls /dev/cu.*
python3 scripts/gps_logger.py            # 포트 자동 탐색, 위경도 뜨는지 확인
python3 scripts/gps_logger.py --demo     # GPS 없이 코드 흐름만 점검

# Starlink 단말 접근 확인 — 맥이 Starlink 네트워크(와이파이)에 연결된 상태에서
ping 192.168.100.1
python3 scripts/starlink_reader.py       # latency/throughput/차폐율 1회 출력
```

GPS는 실내에서 위성을 못 잡는다. 첫 fix는 야외에서 수 분 걸릴 수 있음.

---

## 실행 순서

### 1. 정적 측정 (지점 × 설치환경별, 각 1시간 이상)

```bash
# 예: N1 건물, 창가 개방 조건. caffeinate로 맥 잠자기 방지(필수!)
caffeinate -i python3 scripts/measure_static.py --site N1-window-open --duration 3600

# 단말 텔레메트리 병행 기록 (별도 터미널 또는 tmux 창에서)
caffeinate -i python3 scripts/starlink_reader.py --log --label N1-window-open

# throughput은 ping 측정과 시간을 분리해서 별도 기록 (상향/하향)
iperf3 -c <서버IP> -t 60 -J     > data/raw/static/N1-window-open_iperf_up.json
iperf3 -c <서버IP> -t 60 -J -R  > data/raw/static/N1-window-open_iperf_down.json
```

사이트 라벨 규칙: `{지점}-{환경}`
예) `N1-window-closed`, `N1-window-open`, `N1-rooftop`, `field-open`

### 2. 부하 실험 (다중 사용자 시뮬레이션)

```bash
caffeinate -i python3 scripts/load_test.py --server <서버IP> --clients 1 2 4 8 --duration 60
```

### 3. 이동 측정 (자전거)

```bash
# GPS 포트 자동 탐색. 명시하려면 --gps-port /dev/cu.usbserial-XXXX
caffeinate -i python3 scripts/measure_mobile.py --route dorm-loop
# Ctrl+C로 종료. 시간대/날씨 바꿔 동일 경로 3회 이상 반복 권장
```

### 4. 분석 및 히트맵

```bash
python3 analysis/analyze.py --indir data/raw
python3 analysis/make_heatmap.py --indir data/raw/mobile --out web/heatmap.html
open web/heatmap.html
```

---

## macOS 특이사항 (리눅스 버전과 다른 점)

1. **시리얼 포트 이름**: `/dev/ttyUSB0` → `/dev/cu.usbserial-XXXX` 또는
   `/dev/cu.usbmodemXXXX`. 코드가 `cu.*` 패턴을 자동 탐색한다.
   `tty.*` 말고 `cu.*`를 쓸 것 (tty는 열 때 블로킹될 수 있음).
2. **ping 옵션**: 리눅스 `-W`(초) ≠ macOS `-W`(밀리초). 스크립트가
   `platform.system()`으로 자동 분기하므로 신경 쓸 필요 없음.
3. **잠자기 방지**: 장시간 측정은 반드시 `caffeinate -i <명령>`으로 실행.
   뚜껑 닫고 측정하려면 `caffeinate -is` + 전원 연결 필요.
4. **시계 동기화**: `timedatectl` 대신 `sntp -sS time.apple.com`.
5. **gpsd 불필요**: 맥에선 pyserial 직접 읽기 방식 사용.
6. **설치**: `apt` 대신 `brew`.

## 팁

- 장시간 측정은 tmux 안에서 돌리면 터미널이 닫혀도 유지된다:
  `tmux new -s measure` → 측정 실행 → `Ctrl+b d`로 detach.
- Starlink는 위성 핸드오버로 **약 15초 주기 latency 스파이크**가 보고돼
  있음(IMC'22). RTT 시계열에서 이 주기성을 따로 분석하면 좋은 포인트.
- 모바일 throughput 맵은 점 단위로 성길 수밖에 없다(버스트 동안 이동거리만큼
  공간적으로 번짐). 정밀한 용량 맵은 정적 지점에서 확보하고, 이 한계는
  보고서 "한계점"에 그대로 기술.
