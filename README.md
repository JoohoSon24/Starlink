# Starlink & Local Wi-Fi Measurement Toolkit

macOS 환경에서 Starlink와 일반 Wi-Fi의 연결 품질을 장시간 수집하고 분석하기 위한 실험 도구 모음입니다. 지연시간, 연결 성공률, Starlink 단말 상태, 처리량, GPS 위치를 같은 시간축으로 기록하는 것을 목표로 합니다.

| 항목 | 내용 |
|---|---|
| 프로젝트 기간 | 2026년 7월부터 진행 |
| README 정리일 | 2026-10-13 |
| 역할 | 측정 자동화, GPS·단말 데이터 수집, 분석·시각화 도구 작성 |
| 환경 | macOS, Python, Starlink gRPC, GPS, ping, iperf3 |

## 본인 기여

- 고정·이동 환경용 측정 스크립트 구성
- ping, GPS, Starlink 단말 지표를 UTC 시간축으로 기록
- 실시간 모니터와 처리량 부하 시험 도구 구현
- CSV 결과 분석, 지표 그래프 및 위치 히트맵 생성
- 일반 Wi-Fi 비교 측정 도구 추가
- 위치·네트워크 원본 데이터가 Git에 포함되지 않도록 공개 범위 정리

## 구성

| 폴더 | 내용 |
|---|---|
| [`starlink/`](starlink/) | Starlink 고정·이동 측정, GPS 기록, 부하 시험, 분석 및 시각화 |
| [`localwifi/`](localwifi/) | 일반 Wi-Fi의 게이트웨이/인터넷 연결 상태 장시간 측정 |

```text
.
├── README.md
├── starlink/
│   ├── README.md
│   ├── measure_static.py
│   ├── measure_mobile.py
│   ├── gps_logger.py
│   ├── live_monitor.py
│   ├── load_test.py
│   ├── analyze.py
│   ├── plot_metrics.py
│   └── make_heatmap.py
└── localwifi/
    ├── README.md
    └── measure_static.py
```

## 주요 도구

- `measure_static.py`: 고정 지점에서 ping과 단말 지표 수집
- `measure_mobile.py`: 이동 중 GPS와 네트워크 상태 동시 기록
- `live_monitor.py`: 실시간 상태 모니터링
- `load_test.py`: 다운로드·업로드 및 다중 연결 부하 시험
- `analyze.py`, `plot_metrics.py`, `make_heatmap.py`: 결과 분석과 그래프·히트맵 생성

## 빠른 시작

```bash
cd starlink
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

구체적인 실험 명령과 장비 연결 방법은 [Starlink 실험 가이드](starlink/README.md), 일반 Wi-Fi 측정은 [Local Wi-Fi 가이드](localwifi/README.md)를 참고하세요.

## 데이터 보호

원본 측정 파일에는 위도·경도와 네트워크 정보가 포함될 수 있습니다. 따라서 `data/raw/`와 생성된 분석 결과는 Git 추적에서 제외합니다. 공개 전에는 위치·장비 식별자·내부 주소가 남아 있지 않은지 확인해야 합니다.

## 라이선스

별도 라이선스가 명시되지 않았습니다. 재사용 전에 저장소 소유자의 허가가 필요합니다.
