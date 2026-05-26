"""
VOBC日志解析与智能巡检系统 - FastAPI 后端 v3
- mmap + 帧索引
- 按需分页解析
- SQLite 案例库
"""
import os
import sys
from typing import List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from parser import DataParser, BOARD_SYSTEMS, LABEL_MAP_REVERSE, group_detected
from session import SessionManager
from database import create_case, list_cases, get_case, delete_case, match_cases
from services.inspection import InspectionService
from services.plot import PlotService
from services.data_service import DataService
from services.export_service import ExportService
from services.session_service import SessionService

app = FastAPI(title="VOBC日志解析与智能巡检系统")

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

parser = DataParser()
session_mgr = SessionManager()

RULES_DIR = PROJECT_ROOT / "rules"
INSPECTION_RULES_DIR = RULES_DIR / "inspection"
OUTPUT_DIR = PROJECT_ROOT / "output"
UPLOAD_DIR = PROJECT_ROOT / "log_data" / "uploaded"

inspection_svc = InspectionService(INSPECTION_RULES_DIR)
plot_svc = PlotService()
data_svc = DataService()
export_svc = ExportService(OUTPUT_DIR)
session_svc = SessionService(session_mgr, PROJECT_ROOT, UPLOAD_DIR)


@app.get("/")
async def index():
    html_path = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/boards")
async def get_boards():
    return BOARD_SYSTEMS


@app.get("/api/systems")
async def get_available_systems():
    return {"systems": parser.available_systems()}


@app.post("/api/upload")
async def upload_file(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="未选择文件")

    sorted_files = sorted(files, key=lambda f: f.filename or "")
    session_svc.cleanup_upload_dir()

    saved_paths = []
    saved_names = []

    for file in sorted_files:
        if not file.filename:
            continue
        content = await file.read()
        save_path = session_svc.save_upload_file(file.filename, content)
        saved_paths.append(str(save_path))
        saved_names.append(file.filename)

    if not saved_paths:
        raise HTTPException(status_code=400, detail="未选择有效文件")

    result = session_svc.create_session_from_paths(saved_paths, saved_names)
    if result is None:
        raise HTTPException(status_code=500, detail="文件解析失败")

    return result


@app.post("/api/load")
async def load_local_file(request: Request):
    body = await request.json()
    file_path = body.get("file_path", "").strip()
    multi = body.get("file_paths", [])
    paths = multi if multi else ([file_path] if file_path else [])

    if not paths:
        raise HTTPException(status_code=400, detail="未指定文件路径")

    result = session_svc.load_local_files(paths)
    if result is None:
        raise HTTPException(status_code=400, detail="未解析到任何有效帧")

    return result


@app.post("/api/data")
async def get_data(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    system = body.get("system", "")
    page = body.get("page", 1)
    page_size = body.get("page_size", 10000)

    try:
        session = session_mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在，请先上传日志文件")

    systems = [s.strip() for s in system.split(",") if s.strip()]

    for s in systems:
        if s not in parser.configs:
            raise HTTPException(status_code=400, detail="无解析配置: " + s)

    if len(systems) == 1:
        result = parser.parse_page(
            mmaps=session.mmaps,
            index=session.index,
            system_name=systems[0],
            page=page,
            page_size=page_size,
        )
        result["systems"] = systems
        result["field_systems"] = {
            col: [systems[0]]
            for col in result.get("columns", [])
            if not col.startswith("__")
        }
    else:
        result = data_svc.parse_multi_systems(
            session=session,
            parser=parser,
            LABEL_MAP_REVERSE=LABEL_MAP_REVERSE,
            systems=systems,
            page=page,
            page_size=page_size,
        )

    return result


@app.get("/api/export")
async def export_data(
    session_id: str = Query(...),
    system: str = Query(...),
    format: str = Query("csv"),
):
    try:
        session = session_mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")

    systems = [s.strip() for s in system.split(",")]
    result = export_svc.export(
        session=session,
        parser=parser,
        LABEL_MAP_REVERSE=LABEL_MAP_REVERSE,
        systems=systems,
        format=format,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return FileResponse(
        path=result["path"],
        filename=result["filename"],
        media_type="application/octet-stream",
    )


@app.get("/api/browsedir")
async def browse_directory(base_path: str = Query("")):
    if not base_path:
        base_path = "D:\\"
    if not os.path.isdir(base_path):
        raise HTTPException(status_code=400, detail="路径不存在")
    try:
        entries = []
        for entry in os.scandir(base_path):
            try:
                is_dir = entry.is_dir()
                entries.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_dir": is_dir,
                    "size": entry.stat().st_size if not is_dir else 0,
                })
            except (PermissionError, OSError):
                continue
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return {"path": base_path, "entries": entries}
    except PermissionError:
        raise HTTPException(status_code=403, detail="无权限访问该目录")


@app.get("/api/rules/inspection")
async def get_inspection_rules():
    rules = inspection_svc.get_rules()
    grouped = inspection_svc.get_grouped_rules()
    return {"rules": rules, "grouped": grouped}


@app.post("/api/inspection/check")
async def compliance_check(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    systems = body.get("systems", [])
    selected_rules = body.get("selected_rules", [])

    try:
        session = session_mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")

    return inspection_svc.check(
        session=session,
        parser=parser,
        LABEL_MAP_REVERSE=LABEL_MAP_REVERSE,
        systems=systems,
        selected_rules=selected_rules,
    )


@app.get("/api/cases")
async def api_list_cases(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    system: str = Query(""),
    keyword: str = Query(""),
):
    return list_cases(page=page, size=size, system=system, keyword=keyword)


@app.post("/api/cases")
async def api_create_case(request: Request):
    body = await request.json()
    fields = body.get("fields", [])
    case_id = create_case(
        system=body.get("system", ""),
        serial_no=body.get("serial_no", ""),
        fault_reason=body.get("fault_reason", ""),
        fault_phenomenon=body.get("fault_phenomenon", ""),
        handling=body.get("handling", ""),
        train_no=body.get("train_no", ""),
        event_time=body.get("event_time", ""),
        raw_log=body.get("raw_log", ""),
        fields=fields,
    )
    return {"id": case_id, "status": "created"}


@app.get("/api/cases/{case_id}")
async def api_get_case(case_id: int):
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案例不存在")
    return case


@app.delete("/api/cases/{case_id}")
async def api_delete_case(case_id: int):
    delete_case(case_id)
    return {"status": "deleted"}


@app.post("/api/cases/match")
async def api_match_cases(request: Request):
    body = await request.json()
    system = body.get("system", "")
    field_values = body.get("field_values", {})
    matches = match_cases(system, field_values)
    return {"matches": matches}


@app.post("/api/plot")
async def api_plot(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    system = body.get("system", "")
    fields = body.get("fields", [])
    plot_type = body.get("plot_type", "line")

    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    if not system:
        raise HTTPException(status_code=400, detail="缺少 system")
    if not fields:
        raise HTTPException(status_code=400, detail="缺少 fields")

    try:
        session = session_mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")

    return plot_svc.get_plot_data(
        session=session,
        parser=parser,
        LABEL_MAP_REVERSE=LABEL_MAP_REVERSE,
        system=system,
        fields=fields,
        plot_type=plot_type,
    )


@app.post("/api/get_fields")
async def api_get_fields(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    system = body.get("system", "")

    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    if not system:
        raise HTTPException(status_code=400, detail="缺少 system")

    try:
        session_mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")

    if system not in parser.configs:
        raise HTTPException(status_code=400, detail="无解析配置: " + system)

    fields = plot_svc.get_fields(parser, system)
    return {"fields": fields}


@app.post("/api/get_mappings")
async def api_get_mappings(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    system = body.get("system", "")

    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    if not system:
        raise HTTPException(status_code=400, detail="缺少 system")

    try:
        session_mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")

    if system not in parser.configs:
        raise HTTPException(status_code=400, detail="无解析配置: " + system)

    return plot_svc.get_mappings(parser, system)
