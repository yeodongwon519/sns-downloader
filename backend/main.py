from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from downloaders.youtube import download_youtube, is_youtube_url
from downloaders.twitter import download_twitter, is_twitter_url
from downloaders.instagram import (
    download_instagram,
    download_instagram_post,
    is_instagram_post_url,
)


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

# 미디어는 구글드라이브(vault)에 저장하지 않고 로컬 PC(바탕화면)에만 저장한다.
# 다른 위치로 바꾸려면 DOWNLOAD_DIR 환경변수를 지정하면 된다.
_default_downloads = Path.home() / "Desktop" / "SNS 다운로드"
DOWNLOADS = Path(os.environ.get("DOWNLOAD_DIR", str(_default_downloads))).expanduser()
DOWNLOADS.mkdir(parents=True, exist_ok=True)

ACCESS_TOKEN = os.environ.get("DOWNLOADER_TOKEN", "").strip()

app = FastAPI(title="SNS Downloader")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────── Simple bearer-token auth (optional) ────────────────

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not ACCESS_TOKEN:
        return await call_next(request)

    path = request.url.path
    if path.startswith("/files/") or path == "/health":
        return await call_next(request)

    # Allow frontend assets without token; only API calls require it.
    if request.method == "GET" and (
        path == "/" or path.startswith("/assets/") or path.endswith(".js") or path.endswith(".css") or path.endswith(".html")
    ):
        return await call_next(request)

    cookie_token = request.cookies.get("token", "")
    header_token = request.headers.get("x-token", "")
    bearer = request.headers.get("authorization", "")
    if bearer.startswith("Bearer "):
        bearer = bearer[7:]

    if cookie_token == ACCESS_TOKEN or header_token == ACCESS_TOKEN or bearer == ACCESS_TOKEN:
        return await call_next(request)

    if path.startswith("/api/"):
        return HTMLResponse(status_code=401, content='{"detail":"unauthorized"}', media_type="application/json")

    return await call_next(request)


# ──────────────── Job store ────────────────

class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status: str = "queued"  # queued | running | done | error
        self.progress: float = 0.0
        self.stage: str = "queued"
        self.current: str | None = None
        self.error: str | None = None
        self.result: dict | None = None
        self.files: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 1),
            "stage": self.stage,
            "current": self.current,
            "error": self.error,
            "result": self.result,
            "files": self.files,
        }


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _make_progress(job: Job):
    def cb(info: dict):
        if "progress" in info and info["progress"] is not None:
            job.progress = float(info["progress"])
        if "stage" in info:
            job.stage = info["stage"]
        if "current" in info:
            job.current = info["current"]
    return cb


def _file_meta(p: Path) -> dict:
    try:
        rel = p.resolve().relative_to(DOWNLOADS.resolve())
    except ValueError:
        return {"name": p.name, "url": None, "size": p.stat().st_size if p.exists() else 0}
    url = "/files/" + str(rel).replace("\\", "/")
    return {
        "name": p.name,
        "url": url,
        "size": p.stat().st_size if p.exists() else 0,
    }


# ──────────────── Models ────────────────

class YouTubeReq(BaseModel):
    url: str


class TwitterReq(BaseModel):
    url: str


class InstagramReq(BaseModel):
    target: str
    login_user: str
    login_pass: str
    include_posts: bool = True
    include_highlights: bool = True
    two_factor_code: str | None = None


class InstagramPostReq(BaseModel):
    url: str
    login_user: str
    login_pass: str
    two_factor_code: str | None = None


# ──────────────── API ────────────────

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/youtube")
def api_youtube(req: YouTubeReq):
    url = req.url.strip()
    if not is_youtube_url(url):
        raise HTTPException(400, "올바른 YouTube URL이 아닙니다.")
    job = Job("youtube")
    with _jobs_lock:
        _jobs[job.id] = job

    def run():
        job.status = "running"
        try:
            out_dir = DOWNLOADS / "youtube"
            result = download_youtube(url, out_dir, on_progress=_make_progress(job))
            job.result = result
            if result.get("filepath"):
                job.files = [_file_meta(Path(result["filepath"]))]
            job.progress = 100
            job.status = "done"
            job.stage = "done"
        except Exception as e:
            job.error = str(e)[:500]
            job.status = "error"
            job.stage = "error"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job.id}


@app.post("/api/twitter")
def api_twitter(req: TwitterReq):
    url = req.url.strip()
    if not is_twitter_url(url):
        raise HTTPException(400, "올바른 트위터/X URL이 아닙니다.")
    job = Job("twitter")
    with _jobs_lock:
        _jobs[job.id] = job

    def run():
        job.status = "running"
        try:
            out_dir = DOWNLOADS / "twitter"
            result = download_twitter(url, out_dir, on_progress=_make_progress(job))
            job.result = result
            job.files = [_file_meta(Path(f)) for f in result.get("files", [])]
            job.progress = 100
            job.status = "done"
            job.stage = "done"
        except Exception as e:
            job.error = str(e)[:500]
            job.status = "error"
            job.stage = "error"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job.id}


@app.post("/api/instagram")
def api_instagram(req: InstagramReq):
    if not req.target.strip():
        raise HTTPException(400, "대상 계정을 입력하세요.")
    if not req.login_user.strip() or not req.login_pass.strip():
        raise HTTPException(400, "로그인 정보를 입력하세요.")

    job = Job("instagram")
    with _jobs_lock:
        _jobs[job.id] = job

    def run():
        job.status = "running"
        try:
            out_dir = DOWNLOADS / "instagram"
            result = download_instagram(
                req.target,
                req.login_user,
                req.login_pass,
                out_dir,
                include_posts=req.include_posts,
                include_highlights=req.include_highlights,
                two_factor_code=req.two_factor_code,
                on_progress=_make_progress(job),
            )
            job.result = result
            job.files = [_file_meta(Path(f)) for f in result.get("files", [])[:200]]
            job.progress = 100
            job.status = "done"
            job.stage = "done"
        except Exception as e:
            msg = str(e)[:500]
            if msg == "2FA_REQUIRED":
                job.stage = "two_factor_required"
            job.error = msg
            job.status = "error"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job.id}


@app.post("/api/instagram/post")
def api_instagram_post(req: InstagramPostReq):
    if not is_instagram_post_url(req.url):
        raise HTTPException(400, "올바른 인스타그램 게시물 URL이 아닙니다.")
    if not req.login_user.strip() or not req.login_pass.strip():
        raise HTTPException(400, "로그인 정보를 입력하세요.")

    job = Job("instagram")
    with _jobs_lock:
        _jobs[job.id] = job

    def run():
        job.status = "running"
        try:
            out_dir = DOWNLOADS / "instagram"
            result = download_instagram_post(
                req.url,
                req.login_user,
                req.login_pass,
                out_dir,
                two_factor_code=req.two_factor_code,
                on_progress=_make_progress(job),
            )
            job.result = result
            job.files = [_file_meta(Path(f)) for f in result.get("files", [])]
            job.progress = 100
            job.status = "done"
            job.stage = "done"
        except Exception as e:
            msg = str(e)[:500]
            if msg == "2FA_REQUIRED":
                job.stage = "two_factor_required"
            job.error = msg
            job.status = "error"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


# ──────────────── Static files ────────────────

@app.get("/files/{rel_path:path}")
def serve_file(rel_path: str):
    p = (DOWNLOADS / rel_path).resolve()
    try:
        p.relative_to(DOWNLOADS.resolve())
    except ValueError:
        raise HTTPException(403, "forbidden")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(p, filename=p.name)


@app.get("/")
def index():
    idx = FRONTEND / "index.html"
    if not idx.exists():
        return HTMLResponse("<h1>frontend/index.html이 없습니다.</h1>", status_code=500)
    return FileResponse(idx)


if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8766"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n  → http://localhost:{port}\n")
    if ACCESS_TOKEN:
        print(f"  TOKEN 활성: {ACCESS_TOKEN[:6]}…\n")
    uvicorn.run(app, host=host, port=port, log_level="info")
