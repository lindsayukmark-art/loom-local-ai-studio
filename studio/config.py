from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Hugging Face must never resolve missing assets over the network.
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['DIFFUSERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'


@dataclass
class Settings:
    data_dir: Path
    ollama_url: str = 'http://127.0.0.1:11434'
    text_model: str = 'qwen3:8b'
    image_model_path: str = ''
    video_model_path: str = ''
    voice_model_path: str = ''
    device: str = 'auto'
    enable_local_ai: bool = True

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        parsed = urlparse(self.ollama_url)
        if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}
                or parsed.username or parsed.password or parsed.path not in {'', '/'}
                or parsed.query or parsed.fragment):
            raise ValueError('Ollama must use a loopback HTTP address without credentials or a path.')
        if self.device not in {'auto', 'cpu', 'cuda'}:
            raise ValueError('Device must be auto, cpu, or cuda.')

    @classmethod
    def load(cls):
        default_dir = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'LoomStudio'
        directory = Path(os.environ.get('LOOM_DATA_DIR', default_dir)).expanduser()
        values = {}
        path = directory / 'settings.json'
        if path.is_file():
            values = json.loads(path.read_text(encoding='utf-8'))
        fields = {
            'ollama_url': os.environ.get('LOOM_OLLAMA_URL', values.get('ollama_url', 'http://127.0.0.1:11434')),
            'text_model': os.environ.get('LOOM_TEXT_MODEL', values.get('text_model', 'qwen3:8b')),
            'image_model_path': os.environ.get('LOOM_IMAGE_MODEL_PATH', values.get('image_model_path', '')),
            'video_model_path': os.environ.get('LOOM_VIDEO_MODEL_PATH', values.get('video_model_path', '')),
            'voice_model_path': os.environ.get('LOOM_VOICE_MODEL_PATH', values.get('voice_model_path', '')),
            'device': os.environ.get('LOOM_DEVICE', values.get('device', 'auto')),
        }
        return cls(data_dir=directory, **fields)

    def public(self):
        return {name: getattr(self, name) for name in (
            'ollama_url', 'text_model', 'image_model_path', 'video_model_path', 'voice_model_path', 'device')}

    def save(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.data_dir / ('settings.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(self.public(), indent=2), encoding='utf-8')
        temporary.replace(self.data_dir / 'settings.json')
