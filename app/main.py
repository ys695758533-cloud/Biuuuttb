import hashlib
import io
import logging
import os
import re
import secrets
import threading
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

import imagehash
import psycopg
import torch
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from PIL import Image, ImageOps, UnidentifiedImageError
from transformers import CLIPModel, CLIPProcessor
from app.download_model import MODEL, REVISION

Image.MAX_IMAGE_PIXELS = 20_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
lock = threading.Lock()
security = HTTPBasic()
MAX_BYTES = 10 * 1024 * 1024
model = processor = None

def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)

@asynccontextmanager
async def lifespan(app):
    global model, processor
    if len(os.environ.get("APP_PASSWORD", "")) < 16:
        raise RuntimeError("APP_PASSWORD must contain at least 16 characters")
    for attempt in range(12):
        try:
            with connect() as db:
                db.execute(Path("db/init.sql").read_text())
            break
        except psycopg.OperationalError:
            if attempt == 11:
                raise
            time.sleep(5)
    torch.set_num_threads(2)
    model = CLIPModel.from_pretrained(MODEL, revision=REVISION, local_files_only=True).eval()
    processor = CLIPProcessor.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
    yield

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

def auth(c: HTTPBasicCredentials = Depends(security)):
    valid_user = secrets.compare_digest(c.username.encode(), b"admin")
    valid_pass = secrets.compare_digest(c.password.encode(), os.environ.get("APP_PASSWORD", "").encode())
    if not (valid_user and valid_pass):
        raise HTTPException(401, "用户名或密码不正确", headers={"WWW-Authenticate": "Basic"})

def post_link(value):
    value = value.strip()
    if not value:
        return ""
    match = re.fullmatch(r"https://(?:www\.)?(?:x\.com|twitter\.com)/(?:[A-Za-z0-9_]{1,15}|i/web)/status/(\d+)(?:\?[^#\s]*)?", value)
    if not match:
        raise HTTPException(400, "请填写有效的 X 原帖链接，如 https://x.com/用户名/status/数字")
    return "https://x.com/i/web/status/" + match.group(1)

def features(file):
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "图片不能超过 10 MB")
    try:
        im = Image.open(io.BytesIO(data))
        if im.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError()
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, "请选择有效的 JPG、PNG 或 WebP 图片，像素不超过 2000 万")
    phash = format(int(str(imagehash.phash(im)), 16), "064b")
    with lock, torch.inference_mode():
        vec = model.get_image_features(**processor(images=im, return_tensors="pt"))
        vec = (vec / vec.norm(dim=-1, keepdim=True))[0].tolist()
    im.thumbnail((720, 720))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return hashlib.sha256(data).hexdigest(), phash, str(vec), out.getvalue()

@app.get("/health")
def health():
    try:
        with connect() as db:
            db.execute("SELECT 1 FROM images LIMIT 1")
        if model is None:
            raise RuntimeError()
    except Exception:
        raise HTTPException(503, "服务准备中")
    return {"status": "ok"}

@app.get("/", dependencies=[Depends(auth)])
def home():
    return FileResponse("app/static/index.html")

@app.get("/api/count", dependencies=[Depends(auth)])
def count():
    with connect() as db:
        return {"count": db.execute("SELECT count(*) FROM images").fetchone()[0]}

@app.post("/api/images", dependencies=[Depends(auth)])
def add(file: UploadFile = File(...), post_url: str = Form("")):
    url = post_link(post_url)
    sha, phash, vec, thumb = features(file)
    with connect() as db:
        row = db.execute("INSERT INTO images (sha256,post_url,phash,embedding,thumbnail) VALUES (%s,%s,%s::bit(64),%s::vector,%s) ON CONFLICT (sha256,post_url) DO NOTHING RETURNING id", (sha,url,phash,vec,thumb)).fetchone()
    return {"message": "已加入图片库" if row else "这张图片及链接已在库中"}

@app.post("/api/search", dependencies=[Depends(auth)])
def search(file: UploadFile = File(...), mode: str = Form("hybrid")):
    if mode not in {"hybrid", "phash", "clip"}:
        raise HTTPException(400, "搜索模式无效")
    _, phash, vec, _ = features(file)
    with connect() as db:
        # Retrieve from both indexes so exact pHash matches cannot be lost in CLIP top-k.
        rows = db.execute("""WITH candidates AS (
          (SELECT id FROM images ORDER BY embedding <=> %s::vector LIMIT 100)
          UNION
          (SELECT id FROM images ORDER BY bit_count(phash # %s::bit(64)) LIMIT 100)
        ) SELECT id, post_url, bit_count(phash # %s::bit(64)),
          1 - (embedding <=> %s::vector) FROM images JOIN candidates USING(id)""", (vec,phash,phash,vec)).fetchall()
    results = []
    for id, url, distance, cosine in rows:
        p = 1 - distance / 64
        c = max(0, min(1, float(cosine)))
        score = p if mode == "phash" else c if mode == "clip" else 0.5*p + 0.5*c
        results.append(dict(id=id, post_url=url, phash_distance=distance, clip_similarity=round(c,4), score=round(score,4)))
    return {"results": sorted(results, key=lambda r:r["score"], reverse=True)[:50]}

@app.get("/api/images/{id}", dependencies=[Depends(auth)])
def thumbnail(id: int):
    with connect() as db:
        row = db.execute("SELECT thumbnail FROM images WHERE id=%s", (id,)).fetchone()
    if not row:
        raise HTTPException(404, "图片不存在")
    return Response(bytes(row[0]), media_type="image/jpeg", headers={"Cache-Control":"private, max-age=3600", "X-Content-Type-Options":"nosniff"})

@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    logging.exception("Database operation failed")
    return Response('数据库暂时不可用，请稍后重试', status_code=503)
