import io
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from studio.config import Settings
from studio.main import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(data_dir=Path(self.temp.name), enable_local_ai=False)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def wait(self, job):
        for _ in range(600):
            result = self.client.get('/api/jobs/' + job['id']).json()
            if result['status'] not in {'running', 'queued'}:
                return result
            time.sleep(.01)
        self.fail('Job did not finish')

    def submit(self, **body):
        response = self.client.post('/api/jobs', json={'prompt': 'Test request', **body})
        self.assertEqual(response.status_code, 202, response.text)
        return self.wait(response.json())

    def upload_image(self):
        image = io.BytesIO()
        Image.new('RGB', (80, 60), (255, 80, 20)).save(image, format='PNG')
        response = self.client.post('/api/assets', files={'file': ('../../fake-name.png', image.getvalue(), 'image/png')})
        self.assertEqual(response.status_code, 201, response.text)
        asset = response.json()
        self.assertNotIn('path', asset)
        self.assertEqual(asset['name'], 'fake-name.png')
        return asset

    def test_status_and_local_boundary(self):
        status = self.client.get('/api/status').json()
        self.assertTrue(status['offline'])
        self.assertFalse(status['providers']['image']['available'])
        self.assertEqual(len(status['agents']), 7)
        self.assertEqual(self.client.get('/', headers={'host': 'evil.example'}).status_code, 403)
        response = self.client.post('/api/memories', json={'text': 'injected'}, headers={'origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/memories').json()['memories'], [])
        self.assertEqual(self.client.get('/static/styles.css').status_code, 200)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)

    def test_real_image_edit_and_download(self):
        asset = self.upload_image()
        job = self.submit(kind='edit', asset_id=asset['id'], options={'operation': 'resize', 'width': 40, 'height': 30})
        self.assertEqual(job['status'], 'completed', job['error'])
        output = job['result']['artifacts'][0]
        content = self.client.get(output['url'])
        with Image.open(io.BytesIO(content.content)) as image:
            self.assertEqual(image.size, (40, 30))
        self.assertEqual(job['result']['mode'], 'local_tools')
        self.assertEqual(job['progress'], 100)

    def test_templates_memory_feedback_and_export(self):
        job = self.submit(kind='task', prompt='Write a project checklist')
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(job['result']['mode'], 'template')
        response = self.client.post(f"/api/jobs/{job['id']}/feedback", json={
            'rating': 1, 'note': 'I prefer concise project checklists', 'remember': True})
        self.assertEqual(response.status_code, 200, response.text)
        memories = self.client.get('/api/memories').json()['memories']
        self.assertEqual(len(memories), 1)
        exported = self.client.get('/api/learning/export')
        self.assertEqual(exported.status_code, 200)
        self.assertIn('messages', json.loads(exported.text.splitlines()[0]))
        self.assertEqual(self.client.delete('/api/memories/' + memories[0]['id']).status_code, 200)
        self.assertEqual(self.client.get('/api/memories').json()['memories'], [])

    def test_missing_neural_model_is_failure_not_fake_success(self):
        job = self.submit(kind='image', prompt='A woodland fox')
        self.assertEqual(job['status'], 'failed')
        self.assertIsNone(job['result'])
        self.assertIn('disabled', job['error'].lower())

    def test_untrusted_upload_and_job_parameters_rejected(self):
        response = self.client.post('/api/assets', files={'file': ('fake.png', b'not a media file', 'image/png')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/assets').json()['assets'], [])
        self.assertEqual(self.client.post('/api/jobs', json={'prompt': ' ', 'kind': 'task'}).status_code, 422)
        self.assertEqual(self.client.post('/api/jobs', json={'prompt': 'A', 'kind': 'shell'}).status_code, 422)
        self.assertEqual(self.client.post('/api/jobs', json={'prompt': 'A', 'asset_id': 'missing'}).status_code, 400)
        self.assertEqual(self.client.post('/api/settings', json={'image_model_path': 'https://example.com/model'}).status_code, 422)
        self.assertEqual(self.client.post('/api/settings', json={'text_model': 'test:cloud'}).status_code, 422)

    def test_game_files_csp_and_windows_export(self):
        job = self.submit(kind='game', prompt='Create snake')
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(job['result']['mode'], 'template')
        game, archive = job['result']['artifacts']
        response = self.client.get(game['url'])
        self.assertIn('Mint Snake', response.text)
        self.assertIn('sandbox allow-scripts', response.headers['content-security-policy'])
        self.assertIn("connect-src 'none'", response.headers['content-security-policy'])
        self.assertTrue(self.client.get(archive['url']).content.startswith(b'PK'))
        self.assertIn('attachment', self.client.get(game['url'] + '?download=true').headers['content-disposition'])

    def test_settings_persist_and_reject_changes_during_job(self):
        response = self.client.post('/api/settings', json={'text_model': 'qwen3:4b', 'device': 'cpu'})
        self.assertEqual(response.status_code, 200, response.text)
        saved = json.loads((self.settings.data_dir / 'settings.json').read_text())
        self.assertEqual(saved['text_model'], 'qwen3:4b')
        self.assertEqual(self.app.state.engine.models.settings.device, 'cpu')
        model = self.app.state.engine.models
        async def delayed(*args, **kwargs):
            await asyncio.sleep(.1)
            return 'OK'
        with patch.object(model, 'capabilities', new=AsyncMock(return_value={'reasoning': {'available': True}})), \
             patch.object(model, 'reason', new=delayed):
            queued = self.client.post('/api/jobs', json={'prompt': 'Write a plan', 'kind': 'task'}).json()
            blocked = self.client.post('/api/settings', json={'device': 'auto'})
            self.assertEqual(blocked.status_code, 409)
            self.assertEqual(self.wait(queued)['status'], 'completed')

    def test_common_format_export_is_real_conversion(self):
        asset = self.upload_image()
        job = self.submit(kind='edit', asset_id=asset['id'], options={'operation': 'export', 'format': 'jpg'})
        self.assertEqual(job['status'], 'completed', job['error'])
        output = self.client.get(job['result']['artifacts'][0]['url'])
        self.assertEqual(output.headers['content-type'], 'image/jpeg')
        with Image.open(io.BytesIO(output.content)) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (80, 60))
        for format_name in ('bmp', 'tiff'):
            exported = self.submit(kind='edit', asset_id=asset['id'], options={'operation': 'export', 'format': format_name})
            self.assertEqual(exported['status'], 'completed', exported['error'])
            artifact = exported['result']['artifacts'][0]
            content = self.client.get(artifact['url']).content
            uploaded = self.client.post('/api/assets', files={'file': ('export.' + format_name, content, artifact['mime'])})
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            edited = self.submit(kind='edit', asset_id=uploaded.json()['id'], options={'operation': 'grayscale'})
            self.assertEqual(edited['status'], 'completed', edited['error'])

    def test_generated_program_snippets_download_as_text_without_execution(self):
        model = self.app.state.engine.models
        answer = 'Example program:\n```python\nprint("hello")\n```'
        with patch.object(model, 'capabilities', new=AsyncMock(return_value={'reasoning': {'available': True}})), \
             patch.object(model, 'reason', new=AsyncMock(side_effect=['Write code', answer, 'OK'])):
            job = self.submit(kind='task', prompt='Write a Python program')
        self.assertEqual(job['status'], 'completed', job['error'])
        source = job['result']['artifacts'][1]
        response = self.client.get(source['url'])
        self.assertEqual(response.text.strip(), 'print("hello")')
        self.assertIn('.py', response.headers['content-disposition'])

    def test_premature_oversized_upload_rejected_before_processing(self):
        response = self.client.post('/api/assets', content=b'not-spooled', headers={'content-length': str(100 * 1024 * 1024)})
        self.assertEqual(response.status_code, 413)

    def test_real_reasoning_workflow_with_stubbed_local_model(self):
        model = self.app.state.engine.models
        with patch.object(model, 'capabilities', new=AsyncMock(return_value={'reasoning': {'available': True}})), \
             patch.object(model, 'reason', new=AsyncMock(side_effect=['Plan the steps.', 'Finished writing.', 'OK'])):
            job = self.submit(kind='task', prompt='Write a checklist')
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(job['result']['mode'], 'local_model')
        self.assertEqual(job['result']['text'], 'Finished writing.')
        self.assertIn('reviewer', [event['agent'] for event in job['events']])

    def test_startup_recovers_all_pending_jobs(self):
        store = self.app.state.engine.store
        store.put_job({'id': 'old-job', 'status': 'running', 'events': []})
        store.interrupt_pending()
        self.assertEqual(store.get_job('old-job')['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
