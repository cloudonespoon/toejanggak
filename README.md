# 퇴장각 — 올림픽공원 공연 퇴장 타이밍·출구 안내

공연이 끝난 뒤 **언제, 어느 출구로** 나가야 덜 막히는지 알려주는 정적 웹 서비스입니다.
2026년 한국체육산업개발(주) 공공데이터 활용 경진대회 출품작입니다.

- 서비스: https://cloudonespoon.github.io/toejanggak/
- 데이터: 한국체육산업개발(주) 「올림픽공원 2025 입출차정보」, 「올림픽공원 2025 차량입출차, 공연, 날씨정보 등 연계 데이터」 (문화공공데이터광장 API_CPM_008, API_CPM_009 / 공공데이터포털, 이용허락범위 제한 없음)
- 운영 방법: [OPERATIONS.md](OPERATIONS.md)

## 구성
| 경로 | 내용 |
|---|---|
| `index.html`, `style.css`, `app.js` | 화면 (서버 없이 브라우저에서 동작) |
| `data.js` | 분석 결과 (공연일별 출구별 출차 곡선, 규모별 퇴장 패턴, 백테스트, 운영 권고표) |
| `sw.js`, `manifest.webmanifest`, `icon-*.png` | 오프라인 동작(PWA): 한 번 열면 통신이 끊겨도 안내 |
| `pipeline/` | 데이터 수집(`collect.py`, `download_pages.py`) · 분석(`analyze.py`) · 검사(`validate.py`) |
| `.github/workflows/update-data.yml` | 매주 자동 수집 → 분석 → 검사 → 통과하면 `data.js` 갱신 |

## 구조
```
문화공공데이터광장 API ──(매주, GitHub Actions)──▶ 수집·분석·검사 ──▶ data.js ──▶ GitHub Pages (정적 웹, 운영비 0원)
                                                     └ 실패 시 이전 data.js 유지 + 관리자 메일 알림
```
화면은 API를 직접 부르지 않고 미리 계산한 `data.js`만 읽으므로, API 장애가 있어도 서비스는 멈추지 않습니다.
