import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from studio.overlays import create_overlay


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is not installed')
class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.art = self.root / 'transparent.png'
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((12, 12, 52, 52), fill=(200, 80, 40, 255))
        image.save(self.art)

    def tearDown(self):
        self.temporary.cleanup()

    def alpha_frame(self, path, at='0'):
        result = subprocess.run([
            'ffmpeg', '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe',
            '-c:v', 'libvpx-vp9', '-i', str(path), '-ss', at, '-frames:v', '1',
            '-vf', 'format=rgba', '-threads', '1', '-f', 'image2pipe', '-vcodec', 'png', '-',
        ], check=True, capture_output=True, timeout=30)
        return Image.open(io.BytesIO(result.stdout)).copy()

    def test_webm_decodes_real_alpha_and_motion(self):
        output = self.root / 'overlay.webm'
        info = create_overlay(self.art, output, {'width': 128, 'height': 128, 'duration': 1, 'fps': 8})
        self.assertEqual(info['mime'], 'video/webm')
        self.assertTrue(info['transparent'])
        self.assertEqual(info['frames'], 8)
        self.assertAlmostEqual(info['duration'], 1, delta=.15)
        first = self.alpha_frame(output)
        middle = self.alpha_frame(output, '0.5')
        self.assertEqual(first.size, (128, 128))
        self.assertEqual(first.getchannel('A').getextrema(), (0, 255))
        self.assertNotEqual(first.getchannel('A').getbbox(), middle.getchannel('A').getbbox())
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream_tags=alpha_mode',
                                '-of', 'json', str(output)], check=True, capture_output=True, text=True, timeout=20)
        tags = {key.lower(): value for key, value in json.loads(probe.stdout)['streams'][0]['tags'].items()}
        self.assertEqual(tags['alpha_mode'], '1')

    def test_opaque_art_needs_explicit_key_and_export_remains_visible(self):
        opaque = self.root / 'opaque.png'
        image = Image.new('RGB', (64, 64), '#00ff00')
        ImageDraw.Draw(image).rectangle((20, 20, 44, 44), fill='red')
        image.save(opaque)
        output = self.root / 'keyed.webm'
        with self.assertRaisesRegex(ValueError, 'no transparency'):
            create_overlay(opaque, output, {'width': 128, 'height': 128, 'duration': 1, 'fps': 8})
        info = create_overlay(opaque, output, {'width': 128, 'height': 128, 'duration': 1, 'fps': 8,
                                             'effect': 'still', 'chroma_key': '#00ff00', 'tolerance': 0})
        self.assertTrue(info['transparent'])
        decoded = self.alpha_frame(output)
        self.assertEqual(decoded.getchannel('A').getextrema(), (0, 255))
        r, g, b, alpha = decoded.getpixel((64, 64))
        self.assertGreater(r, g + 100)
        self.assertGreater(alpha, 240)

    def test_all_effects_preserve_transparency(self):
        for effect in ('pulse', 'spin'):
            with self.subTest(effect=effect):
                output = self.root / f'{effect}.webm'
                create_overlay(self.art, output, {'width': 128, 'height': 128, 'duration': 1, 'fps': 8, 'effect': effect})
                self.assertEqual(self.alpha_frame(output).getchannel('A').getextrema(), (0, 255))

    def test_rejects_unbounded_or_unknown_options(self):
        for options in ({'width': 1}, {'width': 129}, {'duration': 11}, {'fps': 60}, {'duration': 10, 'fps': 30},
                        {'effect': 'external'}, {'chroma_key': 'not-a-colour'}, {'tolerance': 10},
                        {'duration': math.nan}, {'shell': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                create_overlay(self.art, self.root / 'bad.webm', options)


if __name__ == '__main__':
    unittest.main()
