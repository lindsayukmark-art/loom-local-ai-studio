import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from studio.config import Settings
from studio.downloads import Downloads, build_source_archive
from studio.main import create_app


class DownloadTests(unittest.TestCase):
    def test_source_zip_excludes_private_files_binaries_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = {
                'README.md': 'Docs', 'studio/main.py': 'source', '.env.example': 'example',
                '.env': 'secret', 'data/studio.sqlite3': 'private', 'models/config.json': 'weights',
                'studio/static/releases/old.zip': 'recursive archive',
                'studio/__pycache__/main.pyc': 'cache', 'packaging/tools/secret.txt': 'private tool',
                '.github/workflows/windows-installer.yml': 'build',
            }
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            (root / 'studio' / 'linked.py').symlink_to(root / '.env')
            with ZipFile(io.BytesIO(build_source_archive(root))) as archive:
                self.assertEqual(set(archive.namelist()), {
                    'LoomStudio/README.md', 'LoomStudio/studio/main.py', 'LoomStudio/.env.example',
                    'LoomStudio/.github/workflows/windows-installer.yml'})

    def test_manifest_checksum_and_current_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'studio').mkdir()
            (root / 'studio/main.py').write_text('source')
            (root / 'README.md').write_text('Guide')
            downloads = Downloads(root)
            manifest = downloads.manifest()
            source = next(item for item in manifest['files'] if item['id'] == 'source')
            data = downloads.file('source')[2]
            self.assertEqual(source['sha256'], hashlib.sha256(data).hexdigest())
            self.assertIn(source['sha256'], downloads.file('checksum')[2].decode())
            self.assertFalse(manifest['installer_available'])
            self.assertIsNone(downloads.file('../../.env'))
            (root / 'studio/extra.py').write_text('new source')
            with ZipFile(io.BytesIO(downloads.file('source')[2])) as archive:
                self.assertIn('LoomStudio/studio/extra.py', archive.namelist())

    def test_packaged_app_uses_bundled_source_without_recursion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            releases = root / 'studio/static/releases'
            releases.mkdir(parents=True)
            downloads = Downloads(root)
            self.assertIsNone(downloads.source())
            (releases / 'LoomStudio-source.zip').write_bytes(b'bundled source')
            self.assertEqual(downloads.source(), b'bundled source')
            (releases / 'LoomStudio-Windows-x64.zip').write_bytes(b'installer archive')
            manifest = downloads.manifest()
            self.assertTrue(manifest['installer_available'])
            windows = next(item for item in manifest['files'] if item['id'] == 'windows-installer')
            self.assertEqual(windows['size'], len(b'installer archive'))

    def test_page_and_real_download_endpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Settings(data_dir=Path(folder), enable_local_ai=False))
            with TestClient(app) as client:
                page = client.get('/download')
                self.assertEqual(page.status_code, 200)
                self.assertIn('source-download', page.text)
                self.assertEqual(client.get('/downloads').status_code, 200)
                self.assertEqual(client.get('/static/download.js').status_code, 200)
                self.assertEqual(client.get('/static/download.css').status_code, 200)
                manifest = client.get('/api/downloads').json()
                source = next(item for item in manifest['files'] if item['id'] == 'source')
                response = client.get(source['url'])
                self.assertEqual(response.status_code, 200)
                self.assertIn('attachment', response.headers['content-disposition'])
                self.assertEqual(hashlib.sha256(response.content).hexdigest(), source['sha256'])
                with ZipFile(io.BytesIO(response.content)) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertIn('LoomStudio/studio/static/download.html', archive.namelist())
                self.assertEqual(client.get('/api/downloads/windows-installer/file').status_code, 404)
                self.assertEqual(client.get('/api/downloads/not-a-file/file').status_code, 404)
                guide = client.get('/api/downloads/windows-guide/file')
                self.assertEqual(guide.status_code, 200)
                self.assertIn('Windows', guide.text)
