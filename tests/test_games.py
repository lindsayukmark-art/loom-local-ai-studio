from pathlib import Path
import json
import re
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from studio.games import GAME_CSP, create_game, create_game_bundle


class GameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_template_is_explicit_and_self_contained(self):
        for prompt, title in [("make snake", "Mint Snake"), ("a space game", "Orbit Runner")]:
            target = self.root / (title + ".html")
            info = create_game(prompt, target)
            content = target.read_text()
            self.assertEqual(info["mode"], "template")
            self.assertEqual(info["title"], title)
            self.assertIn('id="game"', content)
            self.assertIn("requestAnimationFrame", content)
            self.assertIn("Content-Security-Policy", content)
            self.assertNotIn("https://", content)
            self.assertNotIn("<script src", content)

    def test_template_javascript_parses(self):
        for prompt in ["snake", "space"]:
            target = self.root / "game.html"
            create_game(prompt, target)
            script = re.search(r"<script>([\s\S]*?)</script>", target.read_text()).group(1)
            js = self.root / "game.js"
            js.write_text(script)
            try:
                result = subprocess.run(["node", "--check", str(js)], capture_output=True, timeout=10)
            except FileNotFoundError:
                self.skipTest("Node is unavailable for JavaScript parsing")
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_model_html_gets_policy_before_any_script(self):
        target = self.root / "game.html"
        source = '```html\n<!DOCTYPE html><html><head><title>My Game</title><script>let n=1;</script></head><body><canvas></canvas></body></html>\n```'
        result = create_game("custom", target, source)
        content = target.read_text()
        self.assertEqual(result["mode"], "local_model")
        self.assertEqual(result["title"], "My Game")
        self.assertLess(content.index("Content-Security-Policy"), content.index("<script>"))

    def test_external_resources_and_navigation_are_rejected(self):
        for body in [
            '<script src="https://evil.example/x.js"></script>',
            '<img src="local-file.png">',
            '<iframe src="data:text/html,x"></iframe>',
            '<meta http-equiv="refresh" content="0;url=https://example.org">',
            '<script>fetch("https://example.org")</script>',
        ]:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    create_game("x", self.root / "rejected.html", f"<html><body>{body}</body></html>")
                self.assertFalse((self.root / "rejected.html").exists())

    def test_bad_model_output_does_not_become_template(self):
        for source in [
            "I cannot make a game", "<script>alert(1)</script>", "x" * 200001,
            "<html><body><canvas></canvas>",
            "<html><body><script>let n=1;</body></html>",
            "<html><head><style>body{color:red}</head></html>",
            "<html><body><script/></body></html>",
            "<html><body></script></body></html>",
        ]:
            with self.assertRaises(ValueError):
                create_game("x", self.root / "bad.html", source)

    def test_export_has_fixed_paths_and_windows_launcher(self):
        game = self.root / "odd-user-filename.html"
        create_game("snake", game)
        bundle = self.root / "game.zip"
        create_game_bundle(game, bundle)
        with ZipFile(bundle) as archive:
            self.assertEqual(set(archive.namelist()), {"game.html", "Play.cmd", "README.txt"})
            self.assertEqual(archive.read("game.html"), game.read_bytes())
            self.assertIn(b'%~dp0game.html', archive.read("Play.cmd"))
            self.assertIn(b'not a compiled Windows EXE', archive.read("README.txt"))
            self.assertIn(b'preview sandbox is absent', archive.read("README.txt"))
            self.assertIn(b'Disconnect the computer', archive.read("README.txt"))


if __name__ == "__main__":
    unittest.main()
