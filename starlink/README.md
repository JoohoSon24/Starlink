# Starlink 데이터 수집 실험 가이드 (macOS)

이 폴더는 MacBook을 Starlink Wi-Fi에 연결한 뒤 네트워크 상태를 측정하고 CSV로 저장하는 코드이다.

처음 실험한다면 이 문서를 위에서부터 순서대로 따라 하면 된다. 모든 명령어는 터미널에서 `files/starlink` 폴더로 이동한 뒤 실행한다.

```bash
cd /Users/sonjooho/Desktop/Starlink/files/starlink
```

## 1. 무엇을 측정하는가?

| 값 | 쉬운 의미 | 수집 방법 |
|---|---|---|
| Ping RTT | 인터넷이 응답하는 데 걸리는 시간 | Mac에서 `8.8.8.8`로 ping 전송 |
| Ping loss | 보낸 ping 중 응답이 오지 않은 비율 | ping 성공·실패 기록으로 계산 |
| Dish latency | Starlink 안테나에서 Starlink PoP까지의 지연시간 | 안테나 gRPC에서 자동 수집 |
| Downlink | 측정 순간 데이터를 받고 있던 속도 | 안테나 gRPC에서 자동 수집 |
| Uplink | 측정 순간 데이터를 보내고 있던 속도 | 안테나 gRPC에서 자동 수집 |
| Obstruction | 건물이나 나무가 안테나 앞 하늘을 가린 비율 | 안테나 gRPC에서 자동 수집 |
| 위치·속도 | 위도, 경도, 이동속도 | USB GPS에서 자동 수집하거나 고정 좌표 직접 입력 |

`downlink`와 `uplink`는 현재 사용 중인 트래픽이다. 인터넷 회선의 최대 속도는 별도의 iperf3 실험으로 측정해야 한다.

## 2. 위치는 어떻게 입력하는가?

실험 종류에 따라 위치를 받는 방법이 다르다.

| 실험 | 위치 입력 방법 | 좌표를 직접 적어야 하는가? |
|---|---|---|
| 빠른 고정 지점 측정 (`live_monitor.py`) | `--lat`, `--lon`에 한 번 입력 | 선택 사항. 모르면 생략 가능 |
| 정식 고정 지점 측정 (`measure_static.py`) | `--site`에 장소 이름만 입력 | 현재 코드는 위도·경도를 저장하지 않음 |
| 이동 측정 (`measure_mobile.py`) | USB GPS가 매초 자동 입력 | 직접 입력하지 않음 |
| GPS 단독 점검 (`gps_logger.py`) | USB GPS가 자동 입력 | 직접 입력하지 않음 |
| Starlink 단말 기록 (`starlink_reader.py`) | 위치를 수집하지 않음 | 입력하지 않음 |

### 고정 지점의 좌표를 직접 입력할 때

스마트폰 지도 또는 GPS 앱에서 현재 위치의 위도와 경도를 확인한다.

예를 들어 위도 `36.3721`, 경도 `127.3604`라면 다음처럼 입력한다.

```bash
python3 live_monitor.py --site balcony --lat 36.3721 --lon 127.3604
```

- `--site balcony`: 사람이 알아보기 위한 장소 이름이다. 원하는 영문 이름을 사용한다.
- `--lat 36.3721`: 위도이다.
- `--lon 127.3604`: 경도이다.
- 좌표는 모든 CSV 행에 같은 값으로 저장된다. 고정 측정 도중 위치를 이동하면 안 된다.
- 좌표를 모르면 `--lat`, `--lon`을 생략할 수 있다. 이 경우 CSV의 위치 칸은 비어 있다.

```bash
python3 live_monitor.py --site balcony
```

### 이동 측정에서 GPS를 사용할 때

USB GPS가 NMEA 문장을 보내면 코드가 `lat`, `lon`, `speed_kmh`, `num_sats`를 자동으로 읽는다. 따라서 이동 측정에서는 좌표를 직접 적지 않는다. `--route`에는 좌표가 아니라 경로 이름만 적는다.

```bash
python3 measure_mobile.py --route dorm-loop
```

## 3. 최초 한 번 설치

```bash
python3 -m pip install -r requirements.txt
brew install iperf3
```

GPS가 Mac에 나타나지 않을 때만 GPS 장치에 맞는 USB 시리얼 드라이버를 설치한다. CP210x 장치의 예시는 다음과 같다.

```bash
brew install --cask silicon-labs-vcp-driver
```

장시간 실험 전에 macOS의 `시스템 설정 → 일반 → 날짜 및 시간 → 자동으로 설정`을 켠다. 모든 데이터는 UTC 시각으로 저장되므로 여러 CSV를 시간순으로 합치려면 Mac의 시계가 정확해야 한다.

## 4. 실험 전 연결 확인

### 4.1 Starlink 연결 확인

MacBook을 Starlink Wi-Fi에 연결하고 다음 명령어를 실행한다.

```bash
ping -c 3 192.168.100.1
python3 starlink_reader.py
```

첫 번째 명령은 안테나에 접근 가능한지 확인한다. 두 번째 명령에서 Dish latency, drop rate, downlink, uplink, obstruction 등이 나오면 단말 데이터 연결이 정상이다.

단말 연결이 안 되어도 `live_monitor.py`는 종료되지 않고 ping 데이터만 저장한다. 하지만 Dish latency와 obstruction 등의 칸은 비게 된다.

### 4.2 USB GPS 확인

GPS를 연결하기 전과 후에 다음 명령어를 실행해 새로 생긴 포트를 확인한다.

```bash
ls /dev/cu.*
```

보통 `/dev/cu.usbserial-1420`, `/dev/cu.usbmodem14201`, `/dev/cu.SLAB_USBtoUART` 같은 이름이다.

코드가 GPS 포트를 자동으로 찾으므로 우선 다음 명령어만 실행한다.

```bash
python3 gps_logger.py
```

화면에 `lat`, `lon`, `sats`가 나오면 GPS가 정상이다. GPS는 실내에서 위성을 잡지 못할 수 있으므로 하늘이 보이는 야외에서 몇 분간 기다린다.

자동 탐색이 실패하면 확인한 포트를 직접 지정한다.

```bash
python3 gps_logger.py --port /dev/cu.usbserial-1420
```

GPS 장비 없이 프로그램 실행만 시험하려면 가짜 좌표를 사용한다.

```bash
python3 gps_logger.py --demo
python3 measure_mobile.py --route test-route --demo
```

`--demo`로 생성한 좌표는 실제 측정 데이터가 아니므로 연구 결과에 포함하면 안 된다.

## 5. 가장 간단한 고정 지점 실험

처음에는 `live_monitor.py`를 권장한다. 하나의 CSV에 ping과 Starlink 단말 지표를 함께 저장하므로 결과를 바로 확인하기 쉽다.

### 5.1 2분 시험 측정

좌표를 아는 경우:

```bash
python3 live_monitor.py \
  --site balcony \
  --lat 36.3721 \
  --lon 127.3604 \
  --duration 120
```

좌표를 모르는 경우:

```bash
python3 live_monitor.py --site balcony --duration 120
```

`--duration`은 초 단위이다. `--duration`을 생략하면 `Ctrl+C`를 누를 때까지 계속 측정한다.

결과는 `data/raw/live/{장소}_{실행시각}.csv`에 자동 저장된다.

### 5.2 1시간 본 측정

Mac이 잠들지 않도록 `caffeinate -i`를 앞에 붙인다.

```bash
caffeinate -i python3 live_monitor.py \
  --site balcony \
  --lat 36.3721 \
  --lon 127.3604 \
  --duration 3600
```

화면에는 매초 다음과 비슷한 값이 출력되고 같은 내용이 CSV에 저장된다.

```text
ping=50.0ms  dish=42.0ms  ↓0.10/↑0.03Mbps  loss=0.00%  obst=8.10%
```

### 5.3 결과 그래프 만들기

가장 최근 CSV를 자동으로 선택해 그래프를 만든다.

```bash
python3 plot_metrics.py
```

특정 CSV를 선택하려면 경로를 적는다.

```bash
python3 plot_metrics.py data/raw/live/balcony_20260805_165406.csv
```

PNG는 `data/processed/plots/`에 저장된다. 측정 중 그래프를 실시간으로 보고 싶으면 터미널을 하나 더 열어 실행한다.

```bash
python3 plot_metrics.py --live
```

## 6. 정식 고정 지점 실험

`measure_static.py`는 한 장소에서 ping RTT와 끊김을 장시간 측정한다. 시작할 때 traceroute도 함께 저장한다.

현재 이 스크립트는 GPS나 위도·경도를 받지 않는다. 위치는 `--site`에 적은 장소 이름으로만 구분한다. 정확한 좌표가 필요하다면 실험 기록표에 따로 적거나, 고정 지점 실험에는 `live_monitor.py`를 사용한다.

사이트 이름은 `{장소}-{설치환경}` 형식을 권장한다. 예: `N1-window-open`, `N1-window-closed`, `N1-rooftop`, `field-open`.

### 터미널 1: ping 측정

```bash
caffeinate -i python3 measure_static.py \
  --site N1-window-open \
  --duration 3600
```

다음 파일이 생성된다.

```text
data/raw/static/N1-window-open_{시각}.csv
data/raw/static/N1-window-open_{시각}_events.csv
data/raw/static/N1-window-open_{시각}_trace.txt
```

### 터미널 2: Starlink 단말 데이터 동시 기록

새 터미널에서 같은 폴더로 이동한 뒤 실행한다.

```bash
cd /Users/sonjooho/Desktop/Starlink/files/starlink
caffeinate -i python3 starlink_reader.py --log --label N1-window-open
```

단말 데이터는 `data/raw/dish/N1-window-open_{시각}.csv`에 별도 저장된다. 두 터미널은 가능하면 비슷한 시각에 시작한다. 두 파일 모두 UTC 시각을 저장하므로 분석할 때 같은 시간대의 데이터를 연결할 수 있다.

## 7. 이동 실험

준비물은 MacBook, Starlink Mini, USB GPS이다. USB GPS가 위치를 자동 입력하므로 위도와 경도를 직접 적지 않는다.

### 터미널 1: GPS와 ping 동시 기록

```bash
caffeinate -i python3 measure_mobile.py --route dorm-loop
```

`--route dorm-loop`은 실제 좌표가 아니라 경로를 알아보기 위한 이름이다. GPS 자동 탐색이 실패하면 포트를 직접 지정한다.

```bash
caffeinate -i python3 measure_mobile.py \
  --route dorm-loop \
  --gps-port /dev/cu.usbserial-1420
```

이동 실험에는 정해진 종료 시간이 없다. 주행이 끝나면 `Ctrl+C`를 누른다. 결과는 `data/raw/mobile/dorm-loop_{시각}.csv`에 저장된다.

CSV에는 다음 값이 들어간다.

```text
utc_time, lat, lon, speed_kmh, num_sats, rtt_ms, success
```

화면에 `(no GPS fix)`가 계속 나오면 이동을 시작하지 말고 야외에서 GPS 위성 신호를 기다린다.

### 터미널 2: Starlink 단말 데이터 동시 기록

```bash
cd /Users/sonjooho/Desktop/Starlink/files/starlink
caffeinate -i python3 starlink_reader.py --log --label dorm-loop
```

이 파일에는 위치가 들어가지 않는다. 이후 `utc_time`을 기준으로 이동 측정 CSV와 결합한다. 같은 경로를 오전·오후·야간 또는 날씨별로 3회 이상 반복하는 것을 권장한다.

## 8. 다운로드·업로드 속도 실험

정확한 처리량을 측정하려면 iperf3 서버가 별도로 필요하다. 연구실 유선 PC나 클라우드 서버에서 iperf3 서버를 실행하고 그 서버 IP를 알아야 한다.

### 8.1 서버 컴퓨터에서 실행

```bash
iperf3 -s -p 5201
```

### 8.2 Starlink에 연결된 Mac에서 실행

아래 `192.0.2.10`은 예시이므로 실제 iperf3 서버 IP로 바꾼다.

업로드 측정:

```bash
iperf3 -c 192.0.2.10 -t 60 -J > data/raw/static/iperf_upload.json
```

다운로드 측정:

```bash
iperf3 -c 192.0.2.10 -t 60 -J -R > data/raw/static/iperf_download.json
```

iperf3는 인터넷 회선을 강하게 사용하므로 ping RTT가 높아진다. 일반 RTT 측정과 동시에 실행하지 말고 ping 실험이 끝난 뒤 별도로 실행한다.

## 9. 여러 사용자 부하 실험

이 실험은 1명, 2명, 4명, 8명이 동시에 사용할 때 전체 속도와 한 명당 속도가 어떻게 변하는지 확인한다.

서버에서는 5201부터 필요한 수만큼 포트를 각각 열어야 한다. 예를 들어 최대 4개 클라이언트라면 서버 터미널 4개에서 다음을 각각 실행한다.

```bash
iperf3 -s -p 5201
iperf3 -s -p 5202
iperf3 -s -p 5203
iperf3 -s -p 5204
```

Starlink에 연결된 Mac에서 업로드 부하 실험을 실행한다.

```bash
caffeinate -i python3 load_test.py \
  --server 192.0.2.10 \
  --clients 1 2 4 \
  --duration 60
```

다운로드 방향은 `--reverse`를 추가한다.

```bash
caffeinate -i python3 load_test.py \
  --server 192.0.2.10 \
  --clients 1 2 4 \
  --duration 60 \
  --reverse
```

결과 JSON은 `data/raw/load/`에 저장된다.

## 10. 분석과 히트맵 생성

정적·이동 측정 결과를 요약한다.

```bash
python3 analyze.py --indir data/raw
```

결과는 `data/processed/summary.csv`에 저장된다.

이동 측정의 GPS 좌표와 RTT로 지도를 만든다.

```bash
python3 make_heatmap.py \
  --indir data/raw/mobile \
  --out web/heatmap.html
open web/heatmap.html
```

히트맵은 `measure_mobile.py`로 실제 GPS 데이터가 저장된 뒤에 만들 수 있다.

## 11. 실제 실험 당일 전체 명령어

### 고정 지점 실험

```bash
cd /Users/sonjooho/Desktop/Starlink/files/starlink
python3 starlink_reader.py
python3 live_monitor.py --site balcony --lat 36.3721 --lon 127.3604 --duration 120
caffeinate -i python3 live_monitor.py --site balcony --lat 36.3721 --lon 127.3604 --duration 3600
python3 plot_metrics.py
```

### 이동 실험

터미널 1:

```bash
cd /Users/sonjooho/Desktop/Starlink/files/starlink
python3 gps_logger.py
caffeinate -i python3 measure_mobile.py --route dorm-loop
```

터미널 2:

```bash
cd /Users/sonjooho/Desktop/Starlink/files/starlink
caffeinate -i python3 starlink_reader.py --log --label dorm-loop
```

주행 종료 후:

```bash
python3 analyze.py --indir data/raw
python3 make_heatmap.py --indir data/raw/mobile --out web/heatmap.html
open web/heatmap.html
```

## 12. 실험 때 직접 기록할 정보

코드가 자동으로 저장하지 않는 환경 정보는 별도의 실험 기록표에 직접 적는다.

- 날짜와 현지 시각(KST)
- `site` 또는 `route` 이름
- 정확한 위치 또는 출발·도착 위치
- 날씨
- 창문 개방 또는 폐쇄 여부
- 안테나 방향과 설치 높이
- 주변 건물·나무 등 장애물
- 하늘이 보이는 상태의 사진
- 특이사항: 비, 장비 재부팅, Wi-Fi 끊김, 사람이 장비 앞을 가린 경우 등

파일 이름의 `site`·`route`와 기록표 이름을 동일하게 맞추면 나중에 데이터를 구분하기 쉽다.

## 13. 자주 생기는 문제

### Dish 값이 비어 있음

- Mac이 Starlink Wi-Fi에 연결되어 있는지 확인한다.
- `ping -c 3 192.168.100.1`을 실행한다.
- `python3 starlink_reader.py`로 단말 접근을 다시 확인한다.
- ping 측정은 계속되더라도 Dish latency와 obstruction은 비어 있을 수 있다.

### GPS 포트를 찾지 못함

- `ls /dev/cu.*`로 포트를 확인한다.
- `/dev/tty.*`가 아니라 `/dev/cu.*` 포트를 사용한다.
- `--gps-port` 또는 `--port`로 포트를 직접 지정한다.
- GPS 장치에 맞는 USB 시리얼 드라이버가 설치되어 있는지 확인한다.

### GPS 좌표가 비어 있음

- GPS를 하늘이 보이는 야외로 이동한다.
- 첫 위치를 잡을 때까지 몇 분 기다린다.
- `num_sats`가 증가하고 위도·경도가 출력된 뒤 실험을 시작한다.

### 장시간 측정이 중간에 멈춤

- 명령어 앞에 `caffeinate -i`를 붙인다.
- MacBook 덮개를 닫지 않는다.
- 장시간 실험은 전원을 연결한다.

## 14. 파일 구조

```text
files/starlink/
├── live_monitor.py       # 고정 위치 ping + Dish 통합 측정
├── measure_static.py     # 정식 고정 위치 ping 측정
├── measure_mobile.py     # USB GPS + 이동 ping 측정
├── gps_logger.py         # USB GPS 단독 점검
├── starlink_reader.py    # Starlink 단말 데이터 수집
├── load_test.py          # iperf3 다중 사용자 실험
├── plot_metrics.py       # live CSV 그래프 생성
├── analyze.py            # 정적·이동 결과 요약
├── make_heatmap.py       # 이동 결과 지도 생성
├── data/
│   ├── raw/{live,static,mobile,dish,load}/
│   └── processed/plots/
└── web/
```
