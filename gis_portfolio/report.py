import html, json, math
from pathlib import Path


def write_html(path, dataset, report):
    points = [
        f["geometry"]["coordinates"] for f in dataset["assets"] + dataset["centers"]
    ]
    xs, ys = zip(*points)
    xmin, xmax = min(xs) - 0.003, max(xs) + 0.003
    ymin, ymax = min(ys) - 0.003, max(ys) + 0.003

    def xy(p):
        return (
            (p[0] - xmin) / (xmax - xmin) * 960 + 20,
            640 - (p[1] - ymin) / (ymax - ymin) * 600,
        )

    polygons = []
    for name, color in [("zones", "#e4ece1"), ("hazards", "#edc4a5")]:
        for feature in dataset[name]:
            # Even-odd fill preserves Polygon holes in the visual result too.
            shape = " ".join(
                "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in map(xy, ring)) + " Z"
                for ring in feature["geometry"]["coordinates"]
            )
            polygons.append(
                '<path d="'
                + shape
                + f'" fill-rule="evenodd" fill="{color}" stroke="#c6d2bd"><title>'
                + html.escape(feature["properties"]["name"])
                + "</title></path>"
            )
    markers = []
    for row in report["rows"]:
        x, y = xy((row["lon"], row["lat"]))
        markers.append(
            f'<circle class="asset" tabindex="0" role="button" aria-label="{html.escape(row["name"], quote=True)}" data-id="{html.escape(row["id"], quote=True)}" data-priority="{row["priority"]}" cx="{x:.2f}" cy="{y:.2f}" r="7"><title>'
            + html.escape(row["name"])
            + "</title></circle>"
        )
    for feature in dataset["centers"]:
        x, y = xy(feature["geometry"]["coordinates"])
        markers.append(
            f'<rect x="{x - 6:.2f}" y="{y - 6:.2f}" width="12" height="12" fill="#2e4d6b" stroke="white"><title>'
            + html.escape(feature["properties"]["name"])
            + "</title></rect>"
        )
    data = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    source = (
        HTML.replace("@@POLYGONS@@", "".join(polygons))
        .replace("@@MARKERS@@", "".join(markers))
        .replace("@@DATA@@", data)
    )
    Path(path).write_text(source, encoding="utf-8")


HTML = r"""<!doctype html><html lang="ko"><head><link rel="icon" href="data:,"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>시설 점검 우선순위 · GIS 포트폴리오</title><style>
:root{--ink:#283e32;--muted:#6b7a6b;--line:#dae2d4}*{box-sizing:border-box}body{margin:0;background:#f7f9f3;color:var(--ink);font:14px/1.7 "Segoe UI","Malgun Gothic",sans-serif}.shell{width:min(1180px,calc(100% - 40px));margin:auto}header{border-bottom:1px solid var(--line);padding:24px 0;display:flex;justify-content:space-between;gap:20px}header strong{font-size:18px}header span,small{font-size:11px;color:var(--muted)}h1{font-size:30px;letter-spacing:-.04em;margin:34px 0 10px}h2{font-size:15px;margin:0 0 15px}.lead{color:var(--muted);font-size:13px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:26px 0}.metrics>div{border:1px solid var(--line);background:white;padding:16px 22px;border-radius:4px}.metrics span{display:block;font-size:11px;color:var(--muted)}.metrics strong{font-size:27px;font-weight:500}.filters{display:flex;gap:10px;margin:24px 0}input,select,button{font:inherit;border:1px solid #c5d0bf;background:white;border-radius:4px;padding:9px 12px;color:var(--ink)}input{flex:1;min-width:0}button{cursor:pointer;font-size:12px}.layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(230px,1fr);gap:18px}.map{border:1px solid var(--line);background:#eef2e8;border-radius:4px;overflow:hidden}svg{display:block;width:100%;height:auto}.asset{fill:#537f62;stroke:white;stroke-width:2;cursor:pointer}.asset[data-priority=P1]{fill:#bb5945}.asset[data-priority=P2]{fill:#c69a44}.asset:focus,.asset.selected{stroke:#152c20;stroke-width:4;outline:none}.asset[hidden]{display:none}.detail{background:white;border:1px solid var(--line);padding:20px;border-radius:4px}.detail p{font-size:12px}.legend{font-size:11px;color:var(--muted);padding:12px 16px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:14px}.p1{color:#a3402c}.p2{color:#986c20}.p3{color:#427253}.table-wrap{overflow:auto;margin-top:24px;border:1px solid var(--line);border-radius:4px}table{border-collapse:collapse;width:100%;background:white;font-size:12px}th,td{text-align:left;padding:13px;border-bottom:1px solid var(--line)}th{font-weight:500;color:var(--muted);background:#eef2e8}td button{padding:0;border:0;text-align:left;background:none;color:var(--ink)}.empty{text-align:center;padding:25px}.notes{padding:25px 0;color:var(--muted);font-size:11px}.notes p{margin:6px 0}a{color:inherit;text-underline-offset:4px}.status{font-size:12px;color:var(--muted)}footer{border-top:1px solid var(--line);padding:22px 0;font-size:11px;color:var(--muted)}:focus-visible{outline:2px solid #466c3f;outline-offset:3px}@media(max-width:760px){.shell{width:calc(100% - 28px)}.layout{grid-template-columns:1fr}.filters{flex-wrap:wrap}.filters input{flex-basis:100%}.filters select{flex:1;min-width:0}.metrics{gap:8px}.metrics>div{padding:12px}h1{font-size:25px}header span{display:none}table{min-width:650px}}
</style></head><body><div class="shell"><header><strong>시설점검 지도</strong><span>GIS / QGIS · PostgreSQL · PostGIS</span></header><main><h1>어디를 먼저 점검해야 할까요?</h1><p class="lead">시설 상태, 점검 경과, 위험구역과 지원 거점 접근성을 함께 살펴봅니다.</p><section class="metrics" aria-label="분석 요약"><div><span>분석 시설</span><strong id="total"></strong></div><div><span>우선 점검 P1</span><strong id="high"></strong></div><div><span>지원 반경 밖</span><strong id="uncovered"></strong></div></section><div class="filters"><input id="search" type="search" placeholder="시설명 또는 ID 검색" aria-label="시설 검색"><select id="priority" aria-label="우선순위"><option value="">모든 우선순위</option><option>P1</option><option>P2</option><option>P3</option></select><select id="zone" aria-label="구역"><option value="">모든 구역</option></select><button id="download">현재 목록 CSV</button></div><p id="count" class="status" role="status"></p><div class="layout"><div class="map"><svg viewBox="0 0 1000 670" role="img" aria-label="가상 공공시설 우선순위 지도">@@POLYGONS@@@@MARKERS@@</svg><div class="legend"><span class="p1">● P1 우선 점검</span><span class="p2">● P2 검토</span><span class="p3">● P3 일반</span><span>■ 지원 거점</span><span>주황 영역: 가상 위험구역</span></div></div><aside class="detail" id="detail"><h2>시설을 선택하세요</h2><p>지도 또는 목록의 시설명을 누르면 점검 근거를 확인할 수 있습니다.</p></aside></div><div class="table-wrap"><table><thead><tr><th>시설 / ID</th><th>구역</th><th>우선순위</th><th>점수</th><th>최근접 거점</th><th>거리</th><th>점검 근거</th></tr></thead><tbody id="rows"></tbody></table></div><section class="notes"><p id="basis"></p><p>점수: 보수 필요 35 + 점검 180일 초과 25 + 가상 위험구역 25 + 지원 반경 밖 15. P1 ≥60, P2 ≥30, 나머지 P3.</p><p>거리: WGS84 구면 haversine. PostGIS geography의 타원체 거리와 소폭 차이가 있으며, 실제 설계·법정 판정 용도로 사용하지 않습니다.</p><p>지도의 배경·위치·시설은 직접 만든 가상 예제입니다. 실제 공공데이터나 국가사업 수행 실적이 아닙니다.</p><p><a href="analysis.gpkg">GeoPackage</a> · <a href="facility-review.qgs">QGIS 프로젝트</a> · <a href="facilities.csv">전체 CSV</a> · <a href="report.json">분석 JSON</a> · <a href="postgis.sql">PostGIS SQL</a></p></section></main><footer>개인 포트폴리오 · 좌표계 EPSG:4326 · 외부 지도/API 없이 재현할 수 있습니다.</footer></div><script id="report-data" type="application/json">@@DATA@@</script><script>
const report=JSON.parse(document.querySelector('#report-data').textContent);const rows=report.rows;let shown=rows;
document.querySelector('#total').textContent=report.total;document.querySelector('#high').textContent=report.high_priority;document.querySelector('#uncovered').textContent=report.uncovered;document.querySelector('#basis').textContent=`기준일 ${report.as_of} · 지원 반경 ${report.radius_m}m · 가상 시설 ${report.total}개`;
for(const zone of [...new Set(rows.map(r=>r.zone))].sort()){const option=document.createElement('option');option.value=zone;option.textContent=zone;document.querySelector('#zone').append(option)}
function select(id){const row=rows.find(r=>r.id===id);if(!row)return;const box=document.querySelector('#detail');box.replaceChildren();const title=document.createElement('h2');title.textContent=row.name;box.append(title);for(const text of [`${row.id} · ${row.kind}`,`구역: ${row.zone}`,`우선순위: ${row.priority} / ${row.score}점`,`최근접 거점: ${row.nearest_center}`,`거리: ${row.distance_m.toLocaleString()}m / ${row.covered?'반경 안':'반경 밖'}`,`최종 점검: ${row.last_inspected}`,`점검 근거: ${row.reasons}`]){const p=document.createElement('p');p.textContent=text;box.append(p)}document.querySelectorAll('.asset').forEach(e=>e.classList.toggle('selected',e.dataset.id===id))}
function render(){const query=document.querySelector('#search').value.trim().toLocaleLowerCase();const priority=document.querySelector('#priority').value;const zone=document.querySelector('#zone').value;shown=rows.filter(r=>(!priority||r.priority===priority)&&(!zone||r.zone===zone)&&(!query||(r.id+' '+r.name).toLocaleLowerCase().includes(query)));document.querySelector('#count').textContent=`${shown.length} / ${rows.length}개 시설`;const body=document.querySelector('#rows');body.replaceChildren();const ids=new Set(shown.map(r=>r.id));document.querySelectorAll('.asset').forEach(e=>{e.toggleAttribute('hidden',!ids.has(e.dataset.id))});for(const row of shown){const tr=document.createElement('tr');const td=document.createElement('td');const button=document.createElement('button');button.textContent=row.name+' / '+row.id;button.onclick=()=>select(row.id);td.append(button);tr.append(td);for(const value of [row.zone,row.priority,row.score,row.nearest_center,row.distance_m+'m',row.reasons]){const cell=document.createElement('td');cell.textContent=value;tr.append(cell)}body.append(tr)}if(!shown.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=7;td.className='empty';td.textContent='조건에 맞는 시설이 없습니다.';tr.append(td);body.append(tr)}}
for(const id of ['search','priority','zone'])document.querySelector('#'+id).addEventListener('input',render);
document.querySelectorAll('.asset').forEach(e=>{e.onclick=()=>select(e.dataset.id);e.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select(e.dataset.id)}}});
document.querySelector('#download').onclick=()=>{const keys=['id','name','zone','priority','score','distance_m','reasons'];const csv=v=>'"'+String(v).replace(/^[\s]*([=+@-])/g,"'$1").replaceAll('"','""')+'"';const text='\uFEFF'+[keys,...shown.map(r=>keys.map(k=>r[k]))].map(row=>row.map(csv).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='filtered-facilities.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
render();
</script></body></html>"""
