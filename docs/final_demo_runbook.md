# 최종 데모 실행 Runbook

## 목적

이 workflow는 장애물 설치 전후의 반복 주행 데이터를 모아 **관리자가 먼저 확인할 위험 후보 지도**를 만드는 데 목적이 있습니다.

핵심 메시지:

- 이 결과는 휠체어 안전 여부의 최종 판정이 아닙니다.
- IMU/GPS 기반으로 흔들림이 큰 구간을 표시해, 현장 확인과 정비 우선순위를 돕는 관리자용 위험 후보 지도입니다.
- 발표에서는 “위험 확정”보다 “확인해야 할 후보 구간을 빠르게 좁힌다”라고 설명합니다.

## 장애물 전/후 실험 절차

1. 보행자와 차량이 없는 통제 가능한 짧은 경로를 정합니다.
2. `route_name`은 모든 주행에서 동일하게 둡니다. 예: `obstacle_demo_route`
3. `before`는 장애물이 있거나 노면이 거친 상태로 3회 이상 반복 주행합니다.
4. 장애물을 제거하거나 완화한 뒤 같은 경로를 같은 방향, 비슷한 속도로 `after` 3회 이상 반복 주행합니다.
5. 각 세션 직후 `audit-session`으로 GPS valid 비율과 IMU 행 수를 확인합니다.
6. `final-demo`로 전체 세션을 한 번에 집계하고 지도와 리포트를 생성합니다.

안전을 위해 장애물은 낮은 고무 매트, 케이블 프로텍터처럼 통제 가능한 물체만 사용하고, 실제 보행자 통행로에서는 설치하지 않습니다.

## Pi 수집 명령

기본은 카메라 없이 IMU/GPS만 수집합니다. 사진 증거가 필요할 때만 `--no-camera`를 빼고 `--camera-device /dev/video0`를 사용합니다.

정비 전 또는 장애물 있는 상태 반복 수집:

```bash
for i in 1 2 3; do
  python3 -m barrier_free.cli collect \
    --out sessions \
    --duration 120 \
    --rate 20 \
    --phase before \
    --session-id obstacle_before_$(printf "%02d" "$i") \
    --route-name obstacle_demo_route \
    --gps-port /dev/serial0 \
    --no-camera
done
```

정비 후 또는 장애물 제거/완화 상태 반복 수집:

```bash
for i in 1 2 3; do
  python3 -m barrier_free.cli collect \
    --out sessions \
    --duration 120 \
    --rate 20 \
    --phase after \
    --session-id obstacle_after_$(printf "%02d" "$i") \
    --route-name obstacle_demo_route \
    --gps-port /dev/serial0 \
    --no-camera
done
```

세션 품질 확인:

```bash
python3 -m barrier_free.cli audit-session sessions/obstacle_before_01
python3 -m barrier_free.cli audit-session sessions/obstacle_after_01
```

## 최종 데모 생성

```bash
python3 -m barrier_free.cli final-demo sessions \
  --route-name obstacle_demo_route \
  --out web \
  --report-out report \
  --caution-threshold 0.35 \
  --danger-threshold 0.75 \
  --danger-jerk 12
```

생성물:

- `web/demo_data.json`: Leaflet 지도가 읽는 최종 데모 payload
- `report/final_summary.md`: 발표자가 읽을 수 있는 요약 리포트

## 실제 after 수집 전 파이프라인 검증

아직 장애물 제거 후 `after` 세션을 수집하지 못했지만 소프트웨어와 발표 화면을 끝까지 확인해야 할 때는 `mock-after`를 사용합니다.

```bash
python3 -m barrier_free.cli mock-after sessions \
  --route-name campus_test_route \
  --improvement-factor 0.35
```

이 명령은 같은 route의 `before` 세션을 기반으로 `after_mock_<before_session_id>` 세션을 생성합니다. IMU 편차를 줄인 synthetic after이므로 실제 실험 결과로 주장하면 안 됩니다. 발표에서는 “실제 after 수집 전 파이프라인 검증용 mock 데이터”라고 설명합니다.

mock after 생성 후에는 같은 route 이름으로 최종 데모를 만들 수 있습니다.

```bash
python3 -m barrier_free.cli final-demo sessions \
  --route-name campus_test_route \
  --out web \
  --report-out report \
  --caution-threshold 0.35 \
  --danger-threshold 0.75 \
  --danger-jerk 12 \
  --include-synthetic
```

이미 같은 이름의 mock after가 있으면 덮어쓰지 않습니다. 다시 만들려면 `--overwrite`를 명시합니다. 실제 after 세션을 수집한 뒤에는 `--include-synthetic`을 빼서 mock after가 결과에 섞이지 않게 합니다.

## 지도 열기

프로젝트 루트에서 웹 서버를 실행합니다.

```bash
python3 -m http.server 8000
```

브라우저:

```text
http://localhost:8000/web/
```

Pi에서 서버를 띄운 경우:

```text
http://라즈베리파이_IP:8000/web/
```

## Threshold 조정 가이드

기본값은 발표용 시작점입니다.

- `--caution-threshold 0.35`: 약한 흔들림 후보를 노랑으로 표시하는 기준
- `--danger-threshold 0.75`: 강한 충격 후보를 빨강으로 표시하는 기준
- `--danger-jerk 12`: 순간 변화량이 큰 충격을 빨강으로 올리는 기준

조정 원칙:

- 노란 후보가 너무 많으면 `--caution-threshold`를 `0.05`씩 올립니다.
- 확실한 장애물 구간이 빨강으로 잡히지 않으면 `--danger-threshold`를 `0.05`씩 낮추거나 `--danger-jerk`를 `1~2` 낮춥니다.
- GPS valid 비율이 낮거나 경로가 튀면 threshold를 조정하지 말고 다시 수집합니다.
- before와 after 비교에는 반드시 같은 threshold를 사용합니다.
- 발표 자료에는 사용한 threshold 값을 함께 보여줍니다.

## 시연 영상 스토리보드

1. 0-10초: 제목과 핵심 메시지. “최종 안전 판정이 아니라 관리자 위험 후보 지도”
2. 10-25초: Pi 장착 모습, IMU/GPS, 데모 경로와 장애물 소개
3. 25-45초: `before` 반복 주행 수집 화면과 장애물 통과 장면
4. 45-60초: 장애물 제거/완화 뒤 `after` 반복 주행
5. 60-75초: `final-demo` 명령 실행과 리포트 생성 확인
6. 75-100초: 웹 지도에서 노랑/빨강 후보, before/after 비교, 개선 구간 설명
7. 100-120초: `report/final_summary.md` 요약과 한계 문구로 마무리
