"""Behavioral checks for persistence, routing, memory, and dataset boundaries."""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from studio.learning import LearningStore


class LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "learning.sqlite3"
        self.store = LearningStore(self.database)

    def tearDown(self):
        self.directory.cleanup()

    @staticmethod
    def job(id="job-1", kind="task", status="completed", text="Here is a useful answer."):
        return {
            "id": id,
            "prompt": "Plan a small vegetable garden",
            "kind": kind,
            "status": status,
            "result": {"text": text, "artifacts": [{"raw_file_data": "should never appear in export"}]},
        }

    def test_memories_persist_and_can_be_deleted(self):
        memory = self.store.add_memory("Use cinematic blue colors in pictures.")
        reopened = LearningStore(self.database)
        self.assertEqual(reopened.list_memories()[0]["id"], memory["id"])
        self.assertTrue(reopened.delete_memory(memory["id"]))
        self.assertFalse(reopened.delete_memory(memory["id"]))
        self.assertEqual(self.store.stats()["memory_count"], 0)

    def test_retrieval_rejects_unrelated_memories_and_ranks_overlap(self):
        blue = self.store.add_memory("Pictures should use cinematic blue colors.")
        self.store.add_memory("Shopping lists should group vegetables together.")
        relevant = self.store.relevant_memories("Make cinematic pictures in blue")
        self.assertEqual([item["id"] for item in relevant], [blue["id"]])
        self.assertEqual(self.store.relevant_memories("Calculate rocket thrust"), [])
        self.assertEqual(self.store.relevant_memories("blue", limit=0), [])

    def test_only_opted_in_positive_completed_note_becomes_memory(self):
        job = self.job()
        self.store.record_feedback(job, 1, "Prefer concise answers", remember=False)
        self.assertEqual(self.store.stats()["memory_count"], 0)
        self.store.record_feedback(job, -1, "Prefer concise answers", remember=True)
        self.assertEqual(self.store.stats()["memory_count"], 0)
        self.store.record_feedback(self.job(status="failed"), 1, "Prefer concise answers", remember=True)
        self.assertEqual(self.store.stats()["memory_count"], 0)
        self.store.record_feedback(job, 1, "Prefer concise answers", remember=True)
        self.assertEqual(self.store.list_memories()[0]["text"], "Prefer concise answers")
        self.assertEqual(self.store.stats()["feedback_count"], 1)

    def test_rerating_updates_and_retracts_feedback_memory(self):
        job = self.job()
        first = self.store.record_feedback(job, 1, "Prefer blue", remember=True)
        second = self.store.record_feedback(job, 1, "Prefer green", remember=True)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["memory_id"], second["memory_id"])
        self.assertEqual(self.store.stats()["memory_count"], 1)
        self.assertEqual(self.store.stats()["route_examples"], 1)
        self.assertEqual(self.store.list_memories()[0]["text"], "Prefer green")
        self.store.record_feedback(job, -1, "This was not helpful", remember=True)
        self.assertEqual(self.store.stats()["memory_count"], 0)
        self.assertEqual(self.store.stats()["route_examples"], 0)
        self.assertEqual(self.store.export_examples(), "")

    def test_training_deduplicates_normalized_prompts(self):
        self.store.train_route(" Make a poster ", "image")
        self.store.train_route("make   a POSTER", "image")
        self.assertEqual(self.store.stats()["route_examples"], 1)
        # A corrected label replaces the old example instead of counting twice.
        self.store.train_route("make a poster", "task")
        self.assertEqual(self.store.stats()["route_examples"], 1)

    def test_negative_feedback_can_correct_routing_without_learning_rejected_answer(self):
        job = self.job(kind="image")
        self.store.train_route(job["prompt"], "image")
        feedback = self.store.record_feedback(job, -1, "This is a task", remember=True, correct_kind="task")
        self.assertTrue(feedback["route_trained"])
        self.assertEqual(self.store.stats()["route_examples"], 1)
        self.assertEqual(self.store.stats()["memory_count"], 0)
        self.assertEqual(self.store.export_examples(), "")
        with self.store._connect() as connection:
            label = connection.execute("SELECT kind FROM learn_routes").fetchone()[0]
        self.assertEqual(label, "task")

    def test_failed_jobs_do_not_become_feedback_routing_or_export_examples(self):
        feedback = self.store.record_feedback(self.job(status="failed"), 1, "looks good", remember=True)
        self.assertFalse(feedback["learned"])
        self.assertEqual(self.store.stats()["route_examples"], 0)
        self.assertEqual(self.store.export_examples(), "")

    def test_heuristic_baseline_and_no_single_class_hijacking(self):
        self.assertEqual(self.store.predict_route("Draw a picture of a tree")["kind"], "image")
        self.assertEqual(self.store.predict_route("Animate a flower")["kind"], "video")
        self.assertEqual(self.store.predict_route("Crop this photo")["kind"], "edit")
        self.assertEqual(self.store.predict_route("Clean the noise from this podcast audio")["kind"], "audio")
        self.assertEqual(self.store.predict_route("Clean the noise from my voice recording")["kind"], "audio")
        self.assertEqual(self.store.predict_route("Change my voice pitch")["kind"], "voice")
        self.assertEqual(self.store.predict_route("Read this text-to-speech")["kind"], "voice")
        self.assertEqual(self.store.predict_route("Say hello aloud")["kind"], "voice")
        self.assertEqual(self.store.predict_route("Change the voice of this video")["kind"], "voice")
        self.assertEqual(self.store.predict_route("Make an OBS overlay")["kind"], "animation")
        self.assertEqual(self.store.predict_route("Create a transparent animation")["kind"], "animation")
        self.assertEqual(self.store.predict_route("Make a stream stinger")["kind"], "animation")
        self.assertEqual(self.store.predict_route("Create a video of a mountain")["kind"], "video")
        self.assertEqual(self.store.predict_route("Create a Windows snake game")["kind"], "game")
        self.assertEqual(self.store.predict_route("Make a platformer")["kind"], "game")
        self.assertEqual(self.store.predict_route("Draw a snake picture")["kind"], "image")
        self.assertEqual(self.store.predict_route("Plan my week")["kind"], "task")
        for number in range(10):
            self.store.train_route(f"landscape render {number}", "image")
        self.assertEqual(self.store.predict_route("Plan my week"), {"kind": "task", "confidence": 0.35, "learned": False})

    def test_naive_bayes_learns_user_routing_and_persists(self):
        image_prompts = [
            "aurora canvas alpine mountain", "aurora canvas woodland scene",
            "aurora canvas desert dunes", "aurora canvas ocean sunset",
            "aurora canvas winding valley", "aurora canvas flower meadow",
        ]
        task_prompts = [
            "weekly checklist gardening errands", "weekly checklist cleaning kitchen",
            "weekly checklist groceries meal", "weekly checklist schedule meetings",
        ]
        for prompt in image_prompts:
            self.store.train_route(prompt, "image")
        for prompt in task_prompts:
            self.store.train_route(prompt, "task")
        reopened = LearningStore(self.database)
        result = reopened.predict_route("aurora canvas alpine sunset")
        self.assertEqual(result["kind"], "image")
        self.assertTrue(result["learned"])
        self.assertGreaterEqual(result["confidence"], 0.7)
        self.assertFalse(reopened.predict_route("Unrelated orbital mechanics")["learned"])

    def test_export_is_valid_jsonl_with_only_approved_completed_text(self):
        self.store.record_feedback(self.job("approved", text="Plant herbs first.\nThen water them."), 1)
        self.store.record_feedback(self.job("rejected"), -1)
        self.store.record_feedback(self.job("failed", status="failed"), 1)
        self.store.record_feedback(self.job("empty", text=""), 1)
        export = self.store.export_examples()
        lines = export.splitlines()
        self.assertEqual(len(lines), 1)
        example = json.loads(lines[0])
        self.assertEqual([entry["role"] for entry in example["messages"]], ["system", "user", "assistant"])
        self.assertEqual(example["messages"][-1]["content"], "Plant herbs first.\nThen water them.")
        self.assertNotIn("raw_file_data", export)
        self.assertNotIn("should never appear", export)

    def test_all_eight_modalities_are_valid_training_labels(self):
        for kind in ("task", "image", "video", "edit", "audio", "game", "voice", "animation"):
            self.store.train_route(f"Example {kind}", kind)
        self.assertEqual(self.store.stats()["route_examples"], 8)

    def test_workflow_upgrade_preserves_preexisting_examples(self):
        old_database = Path(self.directory.name) / "old-learning.sqlite3"
        with sqlite3.connect(old_database) as connection:
            connection.execute("""CREATE TABLE learn_routes (
                prompt_key TEXT PRIMARY KEY, prompt TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('task','image','video','edit','audio','game')),
                source TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            connection.execute("INSERT INTO learn_routes VALUES (?,?,?,?,?)", (
                "legacy-key", "A legacy game request", "game", "explicit", "2026-01-01T00:00:00+00:00"))
        upgraded = LearningStore(old_database)
        upgraded.train_route("Read this aloud", "voice")
        upgraded.train_route("Create an OBS overlay", "animation")
        self.assertEqual(upgraded.stats()["route_examples"], 3)
        with upgraded._connect() as connection:
            rows = connection.execute("SELECT kind FROM learn_routes ORDER BY kind").fetchall()
        self.assertEqual([row[0] for row in rows], ["animation", "game", "voice"])

    def test_invalid_inputs_have_clear_errors(self):
        for text in ("", " " * 2, "x" * 4001):
            with self.assertRaises(ValueError):
                self.store.add_memory(text)
        with self.assertRaises(ValueError):
            self.store.train_route("Hello", "shell")
        with self.assertRaises(ValueError):
            self.store.record_feedback(self.job(), 0)
        with self.assertRaises(ValueError):
            self.store.record_feedback(self.job(), True)
        with self.assertRaises(ValueError):
            self.store.record_feedback(self.job(), 1, correct_kind="exec")
        with self.assertRaises(ValueError):
            self.store.record_feedback({"prompt": "hello"}, 1)


if __name__ == "__main__":
    unittest.main()
