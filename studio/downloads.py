"""Local release downloads, kept separate from personal media and memory."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import threading
from zipfile import ZIP_DEFLATED, ZipFile

VERSION = '0.1.0'
SOURCE_NAME = 'LoomStudio-source.zip'
ROOT_FILES = {
    'desktop.py', 'README.md', 'INSTALL_WINDOWS.md', 'DELIVERY.md', 'LEARNING.md',
    'LICENSE', 'NOTICE', 'requirements.txt', 'requirements-desktop.txt',
    'requirements-models.txt', 'requirements-voice.txt', '.env.example', '.gitignore',
}
SOURCE_DIRS = {'studio', 'tests', 'packaging', '.github', 'screenshots'}
SOURCE_SUFFIXES = {'.py', '.html', '.css', '.js', '.md', '.txt', '.ps1', '.iss', '.cmd', '.yml', '.yaml', '.png'}
EXCLUDED_DIRS = {'__pycache__', 'releases', 'tools', 'data', 'models', '.git', '.venv', '.venv-build', 'dist', 'build'}


def source_files(root: Path) -> list[Path]:
    """Allowlist project code; never archive local settings, data, or symlinks."""
    root = root.resolve()
    result = []
    candidates = [root / name for name in ROOT_FILES]
    for directory in SOURCE_DIRS:
        base = root / directory
        if not base.is_dir() or base.is_symlink():
            continue
        for current, directories, filenames in os.walk(base, followlinks=False):
            directories[:] = [name for name in directories if name not in EXCLUDED_DIRS
                              and not name.startswith('.') and not (Path(current) / name).is_symlink()]
            candidates.extend(Path(current) / name for name in filenames)
    for path in candidates:
        relative = path.relative_to(root)
        if not path.is_file() or path.is_symlink():
            continue
        if not path.resolve().is_relative_to(root) or any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if any(parent.is_symlink() for parent in path.parents if parent != root and parent.is_relative_to(root)):
            continue
        if len(relative.parts) == 1 and path.name in ROOT_FILES:
            result.append(path)
        elif (len(relative.parts) > 1 and relative.parts[0] in SOURCE_DIRS
              and path.suffix.lower() in SOURCE_SUFFIXES
              and not any(part.startswith('.') for part in relative.parts[1:])):
            result.append(path)
    return sorted(result)


def build_source_archive(root: Path) -> bytes:
    result = io.BytesIO()
    with ZipFile(result, 'w', ZIP_DEFLATED) as archive:
        for path in source_files(root):
            archive.write(path, str(Path('LoomStudio') / path.relative_to(root)))
    return result.getvalue()


class Downloads:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parent.parent
        self.releases = self.root / 'studio' / 'static' / 'releases'
        self._lock = threading.Lock()
        self._source = None
        self._signature = None

    def source(self) -> bytes | None:
        with self._lock:
            # A source checkout offers a current snapshot. Frozen Windows builds
            # include the prebuilt snapshot; they do not contain the source tree.
            if (self.root / 'studio' / 'main.py').is_file() and (self.root / 'README.md').is_file():
                signature = tuple((str(p.relative_to(self.root)), p.stat().st_mtime_ns, p.stat().st_size)
                                  for p in source_files(self.root))
                if signature != self._signature:
                    self._source = build_source_archive(self.root)
                    self._signature = signature
                return self._source
            bundled = self.releases / SOURCE_NAME
            return bundled.read_bytes() if bundled.is_file() and not bundled.is_symlink() else None

    def file(self, file_id: str) -> tuple[str, str, bytes] | None:
        if file_id in {'source', 'checksum'}:
            data = self.source()
            if data is None:
                return None
            if file_id == 'source':
                return SOURCE_NAME, 'application/zip', data
            checksum = hashlib.sha256(data).hexdigest()
            return SOURCE_NAME + '.sha256', 'text/plain', f'{checksum}  {SOURCE_NAME}\n'.encode()
        docs = {'windows-guide': 'INSTALL_WINDOWS.md', 'readme': 'README.md'}
        if file_id in docs:
            path = self.root / docs[file_id]
            return (path.name, 'text/markdown', path.read_bytes()) if path.is_file() and not path.is_symlink() else None
        return None

    def installer_path(self) -> Path | None:
        path = self.releases / 'LoomStudio-Windows-x64.zip'
        return path if path.is_file() and not path.is_symlink() else None

    def manifest(self) -> dict:
        descriptions = [
            ('source', 'Source project', SOURCE_NAME, 'Runnable app source, tests, and Windows installer build files. AI models are separate.'),
            ('windows-installer', 'Windows desktop installer', 'LoomStudio-Windows-x64.zip',
             'Windows installer distribution. Not available until a Windows build is supplied.'),
            ('windows-guide', 'Windows setup guide', 'INSTALL_WINDOWS.md', 'How to build and install the Windows desktop app.'),
            ('readme', 'Project guide', 'README.md', 'Supported tools, offline models, and source setup.'),
            ('checksum', 'Source checksum', SOURCE_NAME + '.sha256', 'SHA-256 checksum for the source ZIP.'),
        ]
        files = []
        for file_id, name, filename, description in descriptions:
            if file_id == 'windows-installer':
                path = self.installer_path()
                files.append({'id': file_id, 'name': name, 'filename': filename, 'description': description,
                              'available': path is not None, 'size': path.stat().st_size if path else None,
                              'url': f'/api/downloads/{file_id}/file' if path else None, 'sha256': None})
                continue
            payload = self.file(file_id)
            data = payload[2] if payload else None
            files.append({'id': file_id, 'name': name, 'filename': filename, 'description': description,
                          'available': data is not None, 'size': len(data) if data is not None else None,
                          'url': f'/api/downloads/{file_id}/file' if data is not None else None,
                          'sha256': hashlib.sha256(data).hexdigest() if data is not None else None})
        return {'version': VERSION, 'files': files,
                'installer_available': next(item['available'] for item in files if item['id'] == 'windows-installer')}
