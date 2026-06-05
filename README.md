# 베리어프리 교내 도로 위험 후보 지도

자전거에 장착한 Raspberry Pi 3B, IMU, GPS, 웹캠을 사용해 교내 오래된 도로의 **소형 바퀴 이동 위험 후보 구간**을 찾고, 정비 전후 개선 정도를 지도에서 확인하는 MVP입니다.

첫 버전은 실제 휠체어 위험을 확정 판정하지 않습니다. 실제 물리 실험 전까지는 deterministic mock 데이터를 사용해 end-to-end 흐름을 개발하고 검증합니다.

## 현재 구현된 흐름

```text
mock 세션 생성
→ 1초 IMU 창 분할
→ 현장/mock 라벨 매칭
→ TinyForestClassifier 학습
→ mock Pi collector 추론 세션 생성
→ 10 m 구간 집계와 before/after 비교
→ Leaflet 관리자 지도용 demo_data.json 생성
```

## 실행

전체 테스트:

```bash
python3 -m unittest discover -s tests -v
```

End-to-end demo 데이터 생성:

```bash
python3 -m barrier_free.cli e2e-demo --out demo_sessions
```

관리자 지도 열기:

```bash
python3 -m http.server 8000
```

브라우저에서 다음 주소를 엽니다.

```text
http://localhost:8000/web/
```

## 주요 산출물

- `demo_sessions/model.json`: mock 라벨로 학습한 모델
- `demo_sessions/mock_collection_run01/`: 모델 추론으로 생성한 mock Pi 수집 세션
- `demo_sessions/demo_data.json`: E2E payload
- `web/demo_data.json`: 웹 지도가 읽는 payload
- `web/index.html`: 관리자 지도

## Raspberry Pi 실제 센서 준비

지원하는 하드웨어:

- IMU: MPU6050, I2C 주소 기본 `0x68`
- GPS: NEO-M8N, UART 기본 `/dev/serial0`, `9600 baud`
- Camera: USB 웹캠, 기본 `/dev/video0`, `fswebcam` 사용

Pi에서 필요한 설정:

```bash
sudo raspi-config
```

- Interface Options에서 I2C 활성화
- Interface Options에서 Serial Port 활성화
- Serial login shell은 비활성화, serial hardware는 활성화

Pi 패키지:

```bash
sudo apt update
sudo apt install -y python3-smbus i2c-tools fswebcam python3-pip
python3 -m pip install pyserial
```

센서 연결 확인:

```bash
i2cdetect -y 1
```

`0x68` 위치에 MPU6050이 보여야 합니다.

프로젝트 health check:

```bash
python3 -m barrier_free.cli check-imu
python3 -m barrier_free.cli check-gps --port /dev/serial0
python3 -m barrier_free.cli check-camera --device /dev/video0 --out camera_check
```

짧은 실제 수집:

```bash
python3 -m barrier_free.cli collect \
  --out sessions \
  --duration 30 \
  --rate 20 \
  --phase before \
  --session-id before_001 \
  --route-name campus_test_route \
  --gps-port /dev/serial0 \
  --camera-device /dev/video0
```

모델을 사용한 추론 수집:

```bash
python3 -m barrier_free.cli collect \
  --out sessions \
  --duration 60 \
  --rate 20 \
  --model demo_sessions/model.json \
  --gps-port /dev/serial0 \
  --camera-device /dev/video0
```

모델 없이 수집하면 `candidate` 이벤트를 저장합니다. 모델을 주면 `caution`/`danger` 이벤트를 저장합니다.

## 수집 직후 지도에서 확인하기

수집 세션 하나만 빠르게 확인할 때는 before/after 비교를 만들 필요 없이 preview 기능을 사용합니다.

지도용 JSON만 생성:

```bash
python3 -m barrier_free.cli preview-session sessions/before_001 --out web
```

지도용 JSON을 생성하고 웹 서버까지 실행:

```bash
python3 -m barrier_free.cli serve-session \
  sessions/before_001 \
  --host 0.0.0.0 \
  --port 8000
```

Pi에서 실행했다면 브라우저에서 다음 주소를 엽니다.

```text
http://라즈베리파이_IP:8000/web/
```

`serve-session`은 실행 직후 `audit-session` 결과도 함께 출력합니다. `ok`가 `false`이면 지도는 볼 수 있지만, `issues`를 보고 GPS, IMU, 사진 누락 문제를 먼저 확인합니다.

## 실제 주행 데이터로 전/후 비교 지도 만들기

1. 정비 전 또는 기준 주행을 수집합니다.

```bash
python3 -m barrier_free.cli collect \
  --out sessions \
  --duration 180 \
  --rate 20 \
  --phase before \
  --session-id before_001 \
  --route-name campus_test_route \
  --gps-port /dev/serial0 \
  --camera-device /dev/video0
```

2. 세션 품질을 확인합니다.

```bash
python3 -m barrier_free.cli audit-session sessions/before_001
```

확인할 핵심 지표:

- `raw_imu_rows`: IMU 행 수
- `gps_valid_ratio`: GPS valid 비율
- `event_count`: 위험 후보 이벤트 수
- `photo_count`: 저장된 사진 수
- `issues`: 데이터 품질 문제

3. 같은 경로를 비교 주행으로 다시 수집합니다. 실제 정비가 없으면 발표용으로는 “정비 후” 대신 “비교 주행”이라고 표현합니다.

```bash
python3 -m barrier_free.cli collect \
  --out sessions \
  --duration 180 \
  --rate 20 \
  --phase after \
  --session-id after_001 \
  --route-name campus_test_route \
  --gps-port /dev/serial0 \
  --camera-device /dev/video0
```

4. before/after 비교 JSON을 생성합니다.

```bash
python3 -m barrier_free.cli compare-sessions \
  --before sessions/before_001 \
  --after sessions/after_001 \
  --out web
```

5. 지도를 엽니다.

```bash
python3 -m http.server 8000
```

브라우저:

```text
http://localhost:8000/web/
```

웹 지도에서 `보기`를 `전/후 비교`로 바꾸면 개선, 악화, 새 위험 구간을 비교 오버레이로 볼 수 있습니다. `after` 주행이 지나가지 않은 구간은 개선으로 계산하지 않고 비교 불가로 둡니다.

## 설계와 계획

- 설계 문서: `docs/superpowers/specs/2026-06-04-barrier-free-road-risk-design.md`
- 구현 계획: `docs/superpowers/plans/2026-06-04-barrier-free-mvp.md`

## 다음 물리 실험 단계

1. 실제 IMU/GPS 모듈을 Pi에 연결한다.
2. 자전거 장착 위치를 고정한다.
3. 예비 주행으로 후보 지점을 찾는다.
4. 단차 높이, 균열 폭, 파임 깊이를 측정해 `label_policy_v1`을 확정한다.
5. mock 라벨 대신 현장 라벨로 모델을 다시 학습한다.
