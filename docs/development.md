# 개발 안내

## 수정할 위치

| 변경 | 파일 (`src/gis_portfolio/` 기준) |
|---|---|
| 명령 옵션·출력 순서 | `cli.py` |
| 입력 검증·거리·점수 | `analysis.py` |
| 지도 구조·스타일·상호작용 | `templates/report.html`, `static/report.css`, `static/report.js` |
| 지도 생성·데이터 삽입 | `report.py` |
| GIS 파일·스타일 | `geopackage.py` |
| DB 테이블·뷰·대조 | `postgis.py` |

HTML·CSS·JavaScript를 별도 파일에서 수정하며, 분석할 때 하나의 독립 HTML로 합칩니다. 외부 지도 API·CDN은 사용하지 않습니다.
화면은 GitHub·[Primer](https://primer.style/product/primitives/color/)를 참고한 흰색 본문·회색 헤더·파란색 링크를 사용합니다. 시설 우선순위는 파랑·주황·빨강으로 표시합니다.

![생성된 지도 화면](images/map-overview.png)

## 입력과 결과

- `data/`: EPSG:4326 Point 시설·거점과 Polygon 관리·위험 구역. 필수 필드는 [데이터 설명](../data/README.md)과 `analysis.py`를 참고합니다.
- `output/report.json`: 기준일·반경·거리 모델·시설별 판정.
- `output/analysis.gpkg`, `facility-review.qgs`: 4개 레이어와 QGIS 상대 경로 프로젝트.
- `output/facilities.csv`, `facilities.geojson`: 분석 속성 포함 시설 목록.
- `output/postgis.sql`: 입력 스냅샷과 분석 뷰.

```powershell
python run.py analyze --as-of 2026-10-26 --radius 1000 --output output-custom
python run.py serve --output output-custom
```

구면 Haversine 거리와 Polygon 경계 포함 여부를 계산합니다. 구멍 내부는 제외합니다. 전체 OGC 위상 검증기·도로망 이동 시간·국가 좌표계 변환·실제 재해 예측은 구현 범위에 포함하지 않습니다.

## PostGIS 대조

Docker와 `psql` 클라이언트를 준비한 뒤 저장소 루트에서 실행합니다. 기존 PostgreSQL도 환경변수로 연결할 수 있습니다.

```powershell
docker compose up -d --wait
$env:PGHOST='127.0.0.1'
$env:PGPORT='55432'
$env:PGUSER='portfolio'
$env:PGDATABASE='portfolio'
$env:PGPASSWORD='portfolio-demo-only'
python run.py database-check
```

기본 비밀번호는 로컬 시연용입니다. Compose의 `POSTGRES_PASSWORD`와 `PGPASSWORD`를 함께 변경합니다. `--psql`로 클라이언트 경로를 지정할 수 있습니다.

SQL은 **`portfolio` 스키마의 네 입력 테이블을 전체 교체**하므로 전용 시연 DB를 사용합니다. PostGIS 확장 생성 권한이 필요합니다. 재분석하면 이전 `database-check.json`을 지우므로 대조도 다시 실행합니다.

기록된 실행은 로컬 PostgreSQL 17.11 / PostGIS 3.6.2입니다. 36행의 판정이 일치했고 구면·타원체 거리 차이는 최대 3.4849m였습니다. 이 표본의 거리 비교 허용치는 5m이며 다른 데이터의 정확도를 보증하지 않습니다.

## 화면 검사

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test-browser.ps1
```

실행 중인 서버, Chrome 또는 Edge와 기본 입력 결과가 필요합니다. CI 설정은 자동 등록하지 않은 [템플릿](ci/verify.yml)입니다.

참고: [PostGIS ST_DWithin](https://postgis.net/docs/ST_DWithin.html), [ST_Covers](https://postgis.net/docs/ST_Covers.html), [GeoPackage](https://www.geopackage.org/spec/).
