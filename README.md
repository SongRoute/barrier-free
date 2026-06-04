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

## 설계와 계획

- 설계 문서: `docs/superpowers/specs/2026-06-04-barrier-free-road-risk-design.md`
- 구현 계획: `docs/superpowers/plans/2026-06-04-barrier-free-mvp.md`

## 다음 물리 실험 단계

1. 실제 IMU/GPS 모듈을 Pi에 연결한다.
2. 자전거 장착 위치를 고정한다.
3. 예비 주행으로 후보 지점을 찾는다.
4. 단차 높이, 균열 폭, 파임 깊이를 측정해 `label_policy_v1`을 확정한다.
5. mock 라벨 대신 현장 라벨로 모델을 다시 학습한다.
