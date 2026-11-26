# 퇴장각 운영 매뉴얼 (2028년까지 유지·이관용)

이 문서만 보고도 다른 사람이 서비스를 이어받아 운영할 수 있도록 정리했습니다.

## 1. 한눈에 보기
| 항목 | 내용 |
|---|---|
| 서비스 주소 | https://cloudonespoon.github.io/toejanggak/ |
| 호스팅 | GitHub Pages (무료, 서버 없음) |
| 운영 비용 | 0원 (GitHub 무료 플랜 범위) |
| 데이터 갱신 | GitHub Actions가 매주 월요일 03:00(한국 시간)에 자동 실행 |
| 장애 시 | 갱신 실패 → 이전 `data.js` 유지, 서비스는 그대로 동작. 실패 메일이 저장소 관리자에게 감 |

## 2. 처음 한 번 설정
1. **API 키 등록**: 저장소 `Settings → Secrets and variables → Actions → New repository secret`
   - `KCISA_API_KEY`: 연계 데이터(API_CPM_009) 키
   - `KCISA_PARKING_KEY`: 입출차정보(API_CPM_008) 키
   - 키는 문화공공데이터광장(culture.go.kr/data) 마이페이지에서 확인. 키를 코드나 문서에 직접 쓰지 마세요.
2. **(권장) 원본 백업 올리기**: `Releases → Draft a new release`, 태그 `data-seed`로 만들고 `raw-data.zip`을 첨부.
   자동 갱신이 처음부터 모든 기록을 다시 받지 않고 이 백업에서 이어받습니다.
3. **Pages 설정**: `Settings → Pages`에서 `Deploy from a branch`, `main` / `(root)`.

## 3. 평소 운영
- 할 일 없음. 매주 자동으로 새 기록을 이어받고, 바뀐 게 있을 때만 `data.js`가 커밋됩니다.
- 수동 실행: `Actions → 데이터 자동 갱신 → Run workflow`.
- 연 2회(3월·9월) 점검: 사이트 접속, `데이터 분석` 탭의 기록 수·갱신 날짜(화면 맨 아래) 확인.

## 4. 문제가 생기면
| 증상 | 원인 | 조치 |
|---|---|---|
| 실패 메일 "입출차 기록 이어받기" | API 서버 응답 지연(504) | 정상. 다음 주에 남은 쪽을 이어받음 |
| 실패 메일 "검사" | 새 결과가 이전보다 기록·공연 수가 적음 | 이전 데이터가 유지됨. 원본이 바뀌었는지 API 확인 |
| 실패 메일 "분석" | 원본 형식 변경 | `pipeline/analyze.py`의 `load_parking`, `load_shows` 확인 |
| 401/403 오류 | API 키 만료 | 키 재발급 후 Secrets 교체 |
| 화면에 "데이터를 불러오지 못했어요" | `data.js` 손상 | 저장소 History에서 이전 `data.js`로 되돌리기 |

## 5. 새 데이터가 공개되면 (예: 2026년 입출차정보)
1. `pipeline/collect.py`의 `API_PARKING`, `API_LINKED`를 새 API ID로 바꾸고 전체 건수에 맞춰 `pipeline/analyze.py`의 `TOTAL_IDS`, 워크플로의 페이지 범위(`1 242`)를 고칩니다.
2. `Run workflow`로 한 번 실행합니다. 검사를 통과하면 자동 반영됩니다.
3. 실시간 출구별 출차 API가 공개되면 `app.js`의 `predict()`에서 2025년 패턴 대신 실시간 값을 쓰도록 바꾸면 됩니다 (화면 구성은 그대로).

## 6. 화면 파일을 고친 뒤 배포할 때
- `index.html`의 `?v=3`과 `sw.js`의 `CACHE` 이름(`toejanggak-v3`)을 같이 올려 주세요 (예: v4). 그래야 휴대폰에 저장된 이전 화면이 새 화면으로 바뀝니다.

## 7. 이관
- 저장소 `Settings → General → Transfer ownership`으로 기관 또는 팀 조직(Organization) 계정에 넘기면 주소·자동 갱신이 그대로 유지됩니다(주소의 계정 이름 부분만 바뀜).
- 넘긴 뒤 Secrets(API 키)를 새 관리자 키로 다시 등록하세요.
