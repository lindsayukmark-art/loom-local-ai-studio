from __future__ import annotations

import asyncio
import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import Settings
from .engine import AGENTS, Engine
from .downloads import Downloads
from .games import GAME_CSP
from .media import inspect_asset
from .providers import LocalModels
from .store import new_id, public_asset

Kind = Literal['auto', 'task', 'image', 'video', 'edit', 'audio', 'voice', 'game', 'animation']
MAX_UPLOAD = 64 * 1024 * 1024


class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt: str = Field(min_length=1, max_length=16000)
    kind: Kind = 'auto'
    asset_id: str | None = Field(default=None, max_length=64)
    options: dict = Field(default_factory=dict)
    use_memory: bool = True

    @field_validator('prompt')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Describe what you want to create.')
        return value.strip()

    @field_validator('options')
    @classmethod
    def bounded_options(cls, value):
        try:
            if len(json.dumps(value, allow_nan=False)) > 8000:
                raise ValueError('Options are too large.')
        except (TypeError, OverflowError):
            raise ValueError('Options must be finite JSON values.') from None
        return value


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rating: Literal[-1, 1]
    note: str = Field(default='', max_length=2000)
    remember: bool = False
    correct_kind: Literal['task', 'image', 'video', 'edit', 'audio', 'voice', 'game', 'animation'] | None = None


class MemoryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator('text')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('A memory cannot be empty.')
        return value.strip()


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text_model: str | None = Field(default=None, min_length=1, max_length=200)
    image_model_path: str | None = Field(default=None, max_length=2048)
    video_model_path: str | None = Field(default=None, max_length=2048)
    voice_model_path: str | None = Field(default=None, max_length=2048)
    device: Literal['auto', 'cpu', 'cuda'] | None = None

    @field_validator('text_model')
    @classmethod
    def local_text_model(cls, value):
        if value is not None and (not value.strip() or 'cloud' in value.lower() or '://' in value):
            raise ValueError('Select the name of an installed local model, not a remote model.')
        return value.strip() if value else value

    @field_validator('image_model_path', 'video_model_path')
    @classmethod
    def local_directory(cls, value):
        if value is None or not value.strip():
            return value.strip() if value else value
        value = value.strip()
        if value.startswith(('\\\\', '//')) or '://' in value:
            raise ValueError('Use a local model folder, not a network path.')
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ValueError('Model folder must be an existing absolute local directory.')
        return str(path.resolve())

    @field_validator('voice_model_path')
    @classmethod
    def voice_file(cls, value):
        if value is None or not value.strip():
            return value.strip() if value else value
        value = value.strip()
        path = Path(value).expanduser()
        if value.startswith(('\\\\', '//')) or '://' in value or not path.is_absolute() or not path.is_file() or path.suffix.lower() != '.onnx':
            raise ValueError('Voice model must be an existing absolute local .onnx file.')
        return str(path.resolve())


def create_app(settings: Settings | None = None):
    settings = settings or Settings.load()
    engine = Engine(settings)
    downloads = Downloads()
    config_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        engine.store.interrupt_pending()
        yield
        await engine.shutdown()

    app = FastAPI(title='Loom — Local AI Studio', version='0.1.0', lifespan=lifespan)
    app.state.engine = engine

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        # Bind to loopback as well. Host validation also prevents DNS rebinding.
        host = request.url.hostname
        if host not in {'127.0.0.1', 'localhost', '::1', 'testserver'}:
            return JSONResponse({'detail': 'Loom is available only on this computer.'}, status_code=403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            expected = f'{request.url.scheme}://{request.url.netloc}'
            if origin and origin != expected:
                return JSONResponse({'detail': 'Cross-origin changes are not allowed.'}, status_code=403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': 'Cross-site changes are not allowed.'}, status_code=403)
        if request.url.path == '/api/assets' and request.method == 'POST':
            try:
                content_length = int(request.headers.get('content-length', '0'))
            except ValueError:
                return JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)
            if content_length > MAX_UPLOAD + 1024 * 1024:
                return JSONResponse({'detail': 'Uploads must be 64 MB or smaller.'}, status_code=413)
        response = await call_next(request)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers.setdefault('Content-Security-Policy',
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            "media-src 'self' blob:; connect-src 'self'; font-src 'self'; frame-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
        return response

    @app.get('/api/status')
    async def status():
        providers = await engine.models.capabilities()
        providers['voice'] = engine.voice.status()
        return {
            'name': 'Loom', 'offline': True,
            'providers': providers,
            'ffmpeg': bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),
            'agents': AGENTS,
            'learning': engine.learning.stats(),
            'active_jobs': sum(job['status'] in {'running', 'queued'} for job in engine.store.jobs()),
            'hardware_hint': 'RTX 3060 / 32 GB RAM: start with Qwen3 4B or 8B Q4 and Stable Diffusion 1.5. Actual speed and model fit depend on VRAM. Video generation is experimental and slow.',
        }

    @app.get('/api/settings')
    async def get_settings():
        return settings.public()

    @app.post('/api/settings')
    async def update_settings(body: SettingsRequest):
        async with config_lock:
            if engine.tasks:
                raise HTTPException(409, 'Wait for queued and running jobs to finish before changing models.')
            changes = body.model_dump(exclude_none=True)
            candidate = Settings(data_dir=settings.data_dir, enable_local_ai=settings.enable_local_ai,
                                 **(settings.public() | changes))
            await asyncio.to_thread(candidate.save)
            for key, value in changes.items():
                setattr(settings, key, value)
            engine.models = LocalModels(settings)
            engine.voice = engine.voice.__class__(settings)
            return settings.public()

    @app.get('/api/jobs')
    async def list_jobs():
        return {'jobs': engine.store.jobs()}

    @app.get('/api/jobs/{job_id}')
    async def get_job(job_id: str):
        job = engine.store.get_job(job_id)
        if not job:
            raise HTTPException(404, 'Job not found.')
        return job

    @app.post('/api/jobs', status_code=202)
    async def submit_job(body: JobRequest):
        async with config_lock:
            if engine.closing:
                raise HTTPException(503, 'Loom is closing.')
            if len(engine.tasks) >= 12:
                raise HTTPException(429, 'The local queue is full. Wait for a job to finish.')
            try:
                return engine.submit(body)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from None

    @app.post('/api/jobs/{job_id}/feedback')
    async def feedback(job_id: str, body: FeedbackRequest):
        job = engine.store.get_job(job_id)
        if not job:
            raise HTTPException(404, 'Job not found.')
        if job['status'] != 'completed':
            raise HTTPException(409, 'Feedback is available for completed jobs.')
        return engine.learning.record_feedback(job, **body.model_dump())

    @app.get('/api/assets')
    async def list_assets():
        return {'assets': [public_asset(item) for item in engine.store.assets()]}

    @app.post('/api/assets', status_code=201)
    async def upload(file: UploadFile = File(...)):
        temporary = engine.asset_dir / (new_id() + '.upload')
        try:
            total = 0
            with temporary.open('wb') as output:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413, 'Uploads must be 64 MB or smaller.')
                    output.write(chunk)
            metadata = await asyncio.to_thread(inspect_asset, temporary)
            suffix = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp',
                      'image/bmp': '.bmp', 'image/tiff': '.tiff',
                      'image/gif': '.gif', 'video/mp4': '.mp4', 'video/webm': '.webm',
                      'video/x-msvideo': '.avi', 'audio/wav': '.wav', 'audio/mpeg': '.mp3',
                      'audio/mp4': '.m4a', 'audio/flac': '.flac', 'audio/ogg': '.ogg'}.get(metadata['mime'], '.media')
            destination = temporary.with_suffix(suffix)
            temporary.replace(destination)
            # Names are display-only; they never become paths.
            name = (file.filename or 'uploaded-media').replace('\\', '/').split('/')[-1][:180]
            return engine.register(destination, name, metadata)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        finally:
            temporary.unlink(missing_ok=True)
            await file.close()

    @app.get('/api/assets/{asset_id}/file')
    async def asset_file(asset_id: str, download: bool = False):
        asset = engine.store.get_asset(asset_id)
        if not asset:
            raise HTTPException(404, 'Asset not found.')
        path = Path(asset['path']).resolve()
        if not path.is_relative_to(engine.asset_dir.resolve()) or not path.is_file():
            raise HTTPException(404, 'Local file is unavailable.')
        headers = {}
        if asset['kind'] == 'game':
            headers['Content-Security-Policy'] = GAME_CSP + "; sandbox allow-scripts; frame-ancestors 'self'"
        attachment = download or asset['kind'] in {'archive', 'document'}
        return FileResponse(path, media_type=asset['mime'],
                            filename=asset['name'] if attachment else None, headers=headers)

    @app.get('/api/memories')
    async def get_memories():
        return {'memories': engine.learning.list_memories()}

    @app.post('/api/memories', status_code=201)
    async def remember(body: MemoryRequest):
        return engine.learning.add_memory(body.text)

    @app.delete('/api/memories/{memory_id}')
    async def forget(memory_id: str):
        if not engine.learning.delete_memory(memory_id):
            raise HTTPException(404, 'Memory not found.')
        return {'deleted': True}

    @app.get('/api/learning')
    async def learning():
        return engine.learning.stats() | {
            'explanation': 'Saved preferences and a small supervised routing classifier learn locally. '
                           'Feedback does not change the underlying language, image, or video model weights.'}

    @app.get('/api/learning/export')
    async def export_learning():
        return Response(engine.learning.export_examples(), media_type='application/x-ndjson',
                        headers={'Content-Disposition': 'attachment; filename="approved-examples.jsonl"'})

    static_dir = Path(__file__).resolve().parent / 'static'

    @app.get('/download', include_in_schema=False)
    @app.get('/downloads', include_in_schema=False)
    async def download_page():
        return FileResponse(static_dir / 'download.html', media_type='text/html')

    @app.get('/api/downloads')
    async def download_manifest():
        return await asyncio.to_thread(downloads.manifest)

    @app.get('/api/downloads/{file_id}/file')
    async def download_release(file_id: str):
        if file_id == 'windows-installer':
            installer = downloads.installer_path()
            if installer:
                return FileResponse(installer, media_type='application/zip', filename=installer.name)
        payload = await asyncio.to_thread(downloads.file, file_id)
        if payload is None:
            raise HTTPException(404, 'This download is not available. A compiled Windows installer has not been supplied.')
        filename, mime, content = payload
        return Response(content, media_type=mime,
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    app.mount('/static', StaticFiles(directory=static_dir), name='static')
    app.mount('/', StaticFiles(directory=static_dir, html=True), name='studio')
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=8765)
