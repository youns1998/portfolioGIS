# 시설 점검 GIS

시설 상태·점검일·지원 거점 거리로 점검 우선순위를 계산하고 지도와 GIS 파일로 내보냅니다. 입력은 직접 만든 가상 시설 36개입니다.

**Python 3.11+ · GeoJSON · GeoPackage · PostgreSQL/PostGIS**

## 실행

추가 Python 패키지 없이 저장소 루트에서 실행합니다.

```powershell
python run.py analyze
python run.py serve
```

접속: **http://127.0.0.1:8787/**. 생성한 `output/index.html`은 파일로 직접 열어도 작동합니다.

## 기능

- GeoJSON 형식·필수 속성·좌표·ID·날짜 검증
- 최근접 지원 거점, 반경 포함 여부, 관리·위험 구역 분석
- 우선순위·구역·시설 검색, 지도·표 동기화, 시설별 판정 근거
- CSV·GeoJSON·GeoPackage·QGIS 프로젝트·PostGIS 분석 SQL 생성

기본 기준일 `2026-10-25`, 지원 반경 `750m`. 보수 필요 35 + 점검 180일 초과 25 + 위험 구역 25 + 반경 밖 15점으로 계산하며, P1은 60점 이상, P2는 30점 이상입니다. 기관 기준이 아닌 예시 규칙입니다.

## 코드 구조

```text
run.py                      # 실행 진입점
src/gis_portfolio/
  cli.py                    # 명령 처리·분석 흐름
  analysis.py               # 입력 검증·거리·우선순위
  report.py                 # 독립 HTML 보고서 생성
  templates/ · static/      # 지도 HTML·CSS·JavaScript
  geopackage.py             # GeoPackage·QGIS 파일 생성
  postgis.py                # SQL 생성·DB 대조
data/ · tests/ · output/    # 원본 가상 데이터·테스트·생성 결과
```

처음 읽을 코드: [CLI](src/gis_portfolio/cli.py) → [분석 규칙](src/gis_portfolio/analysis.py) → [테스트](tests/test_analysis.py).

## 검증

```powershell
python -m unittest discover -s tests -v
```

**Python 테스트 21개**, 실제 브라우저 검사 10개 통과. 기본 결과는 시설 36개 / P1 7개 / 반경 밖 19개입니다. 실제 PostGIS와 36개 시설의 거점·판정·점수·등급을 대조했습니다.

입출력은 EPSG:4326입니다. Python은 구면 거리, PostGIS는 타원체 거리를 사용하므로 경계 부근의 판정이 달라질 수 있습니다. QGIS 데스크톱에서 직접 여는 검증은 수행하지 않았습니다.

[지도 화면·개발·DB 실행 안내](docs/development.md) · [검증 기록](docs/verification.md) · [가상 데이터](data/README.md)
