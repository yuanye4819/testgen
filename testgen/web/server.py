"""
TestGen Web API Server
FastAPI backend that wraps the testgen engine as REST endpoints.
"""

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from ..core.models import InputSource, OutputFormat, TestType
from ..orchestrator import Orchestrator

app = FastAPI(title="TestGen 测试用例生成平台", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mapping dictionaries for the API
INPUT_SOURCE_MAP = {
    "openapi": InputSource.OPENAPI,
    "code": InputSource.SOURCE_CODE,
    "nl": InputSource.NATURAL_LANG,
    "url": InputSource.URL,
}

OUTPUT_FORMAT_MAP = {
    "pytest": OutputFormat.PYTEST,
    "json": OutputFormat.JSON,
    "yaml": OutputFormat.YAML,
    "excel": OutputFormat.EXCEL,
    "csv": OutputFormat.CSV,
}

TEST_TYPE_MAP = {
    "api": TestType.API,
    "unit": TestType.UNIT,
    "e2e": TestType.E2E,
    "integration": TestType.INTEGRATION,
    "perf": TestType.PERFORMANCE,
    "functional": TestType.FUNCTIONAL,
}


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.0", "timestamp": datetime.now().isoformat()}


@app.post("/api/generate")
async def generate_tests(
    file: UploadFile = File(None),
    text_input: str = Form(""),
    source: str = Form("openapi"),
    output_format: str = Form("pytest"),
    test_types: str = Form(""),
    llm_enabled: bool = Form(False),
    llm_model: str = Form("deepseek-chat"),
    temperature: float = Form(0.3),
    max_cases: int = Form(5),
    max_unit_cases: int = Form(3),
    base_url_api: str = Form("http://localhost:8000"),
    llm_api_key: str = Form(""),
    llm_base_url: str = Form(""),
):
    """
    Generate test cases from uploaded file or text input.
    
    Returns JSON with output file paths and a downloadable zip URL.
    """
    # Create a unique work directory
    job_id = uuid.uuid4().hex[:12]
    work_dir = Path(tempfile.gettempdir()) / f"testgen_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir = work_dir / "output"

    try:
        # Determine input path
        input_path = ""
        if file and file.filename:
            # Save uploaded file to work dir
            file_content = await file.read()
            filepath = work_dir / file.filename
            filepath.write_bytes(file_content)
            input_path = str(filepath)
        elif text_input.strip():
            # URL 模式直接传原始 URL，不保存为文件
            if source == "url":
                input_path = text_input.strip()
            else:
                ext_map = {
                    "openapi": ".yaml" if text_input.strip().startswith("openapi:") or text_input.strip().startswith("---") else ".json",
                    "code": ".py",
                    "nl": ".txt",
                }
                ext = ext_map.get(source, ".txt")
                filepath = work_dir / f"input{ext}"
                filepath.write_text(text_input.strip(), encoding="utf-8")
                input_path = str(filepath)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": "请上传文件或输入文本内容。"},
            )

        # Parse test types
        parsed_types = []
        if test_types:
            parsed_types = [TEST_TYPE_MAP[t.strip()] for t in test_types.split(",") if t.strip() in TEST_TYPE_MAP]

        # 注入 API 密钥到环境变量（LLM 客户端从此读取）
        if llm_enabled:
            if llm_api_key:
                os.environ["OPENAI_API_KEY"] = llm_api_key
            if llm_base_url:
                os.environ["OPENAI_BASE_URL"] = llm_base_url

        # Run orchestrator
        orchestrator = Orchestrator()
        result = orchestrator.run(
            input_source=INPUT_SOURCE_MAP[source],
            output_format=OUTPUT_FORMAT_MAP[output_format],
            input_path=input_path,
            test_types=parsed_types,
            llm_enabled=llm_enabled,
            llm_model=llm_model,
            llm_temperature=temperature,
            output_dir=str(output_dir),
            base_url=base_url_api,
            max_cases_per_endpoint=max_cases,
            max_cases_per_function=max_unit_cases,
        )

        if not result["success"]:
            return JSONResponse(
                status_code=500,
                content={"error": result.get("error", "生成失败")},
            )

        # Collect output files as base64 for preview
        preview_files = []
        for fp in result["output_files"]:
            p = Path(fp)
            if p.exists() and p.suffix in (".py", ".json", ".yaml", ".yml", ".csv"):
                try:
                    content = p.read_text(encoding="utf-8")
                    preview_files.append({
                        "name": p.name,
                        "path": str(p.relative_to(output_dir)),
                        "content": content,
                        "language": _guess_language(p.suffix),
                    })
                except Exception:
                    pass
            elif p.exists() and p.suffix == ".xlsx":
                preview_files.append({
                    "name": p.name,
                    "path": str(p.relative_to(output_dir)),
                    "content": None,
                    "language": "excel",
                    "download_url": f"/api/download/{job_id}/{p.name}",
                })

        # Store job directory reference for later download
        _active_jobs[job_id] = str(work_dir)

        return {
            "success": True,
            "job_id": job_id,
            "suites_count": result["suites_count"],
            "total_cases": result["total_cases"],
            "output_files": [str(Path(f).name) for f in result["output_files"]],
            "preview_files": preview_files,
            "download_all_url": f"/api/download-all/{job_id}",
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# In-memory job store (cleared on restart)
_active_jobs: dict[str, str] = {}


@app.get("/api/download/{job_id}/{filename}")
async def download_file(job_id: str, filename: str):
    """Download a single output file."""
    work_dir = _active_jobs.get(job_id)
    if not work_dir:
        return JSONResponse(status_code=404, content={"error": "Job not found or expired"})

    filepath = Path(work_dir) / "output" / filename
    # Also try subdirectories
    if not filepath.exists():
        for root in (Path(work_dir) / "output").rglob(filename):
            filepath = root
            break

    if not filepath.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})

    media_type = "application/octet-stream"
    if filepath.suffix == ".xlsx":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filepath.suffix == ".csv":
        media_type = "text/csv"
    elif filepath.suffix == ".json":
        media_type = "application/json"
    elif filepath.suffix == ".py":
        media_type = "text/plain"

    return FileResponse(str(filepath), filename=filepath.name, media_type=media_type)


@app.get("/api/download-all/{job_id}")
async def download_all(job_id: str):
    """Download all output files as a zip archive."""
    import zipfile
    import io

    work_dir = _active_jobs.get(job_id)
    if not work_dir:
        return JSONResponse(status_code=404, content={"error": "Job not found or expired"})

    output_path = Path(work_dir) / "output"
    if not output_path.exists():
        return JSONResponse(status_code=404, content={"error": "No output files found"})

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in output_path.rglob("*"):
            if fp.is_file():
                zf.write(fp, fp.relative_to(output_path))

    buf.seek(0)
    return FileResponse(
        buf,
        media_type="application/zip",
        filename=f"testgen_output_{job_id}.zip",
    )


def _guess_language(suffix: str) -> str:
    """Guess the highlight language from file extension."""
    return {
        ".py": "python",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".csv": "text",
    }.get(suffix, "text")


# Serve static frontend
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    """Serve the main frontend page."""
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))
