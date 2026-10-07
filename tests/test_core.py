import json
import os
from pathlib import Path
import tempfile
import unittest

from organizer.core import execute, forget_history, has_history, history_token, preview, undo


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "下载"
        self.root.mkdir()
        self.history = Path(self.temp.name) / "history"

    def file(self, name, data=b"original"):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_preview_classifies_without_writing_and_skips_non_files(self):
        self.file("照片.JPG")
        self.file("说明.pdf")
        self.file("archive.zip")
        self.file("setup.exe")
        self.file("unknown.xyz")
        self.file("partial.crdownload")
        self.file("partial.part")
        self.file(".hidden.txt")
        (self.root / "子目录").mkdir()
        before = set(self.root.iterdir())
        plan = preview(self.root)
        self.assertEqual({i.source.name: i.destination.parent.name for i in plan.items}, {
            "照片.JPG": "图片", "说明.pdf": "文档", "archive.zip": "压缩包",
            "setup.exe": "安装包", "unknown.xyz": "其他",
        })
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertEqual(plan.skipped, 4)

    def test_move_and_persistent_undo_restore_exact_bytes(self):
        self.file("说明.txt", b"contents")
        result = execute(preview(self.root), self.history)
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.errors, [])
        self.assertFalse((self.root / "说明.txt").exists())
        self.assertEqual((self.root / "文档" / "说明.txt").read_bytes(), b"contents")
        self.assertTrue(has_history(self.history))
        restored = undo(Path(str(self.history)))
        self.assertEqual(restored.completed, 1)
        self.assertEqual((self.root / "说明.txt").read_bytes(), b"contents")
        self.assertFalse(has_history(self.history))

    def test_existing_and_post_preview_collisions_do_not_overwrite(self):
        self.file("说明.txt", b"new")
        target = self.root / "文档"
        target.mkdir()
        (target / "说明.txt").write_bytes(b"old")
        plan = preview(self.root)
        self.assertEqual(plan.items[0].destination.name, "说明 (1).txt")
        (target / "说明 (1).txt").write_bytes(b"raced")
        result = execute(plan, self.history)
        self.assertEqual(result.completed, 1)
        self.assertEqual((target / "说明.txt").read_bytes(), b"old")
        self.assertEqual((target / "说明 (1).txt").read_bytes(), b"raced")
        self.assertEqual((target / "说明 (2).txt").read_bytes(), b"new")

    def test_changed_source_is_reported_and_left_in_place(self):
        source = self.file("notes.txt")
        plan = preview(self.root)
        source.write_bytes(b"changed since preview")
        result = execute(plan, self.history)
        self.assertEqual(result.completed, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(source.read_bytes(), b"changed since preview")

    def test_undo_conflict_keeps_history_for_retry(self):
        source = self.file("notes.txt")
        execute(preview(self.root), self.history)
        source.write_bytes(b"new unrelated file")
        result = undo(self.history)
        self.assertEqual(result.completed, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(source.read_bytes(), b"new unrelated file")
        self.assertTrue(has_history(self.history))
        source.unlink()
        self.assertEqual(undo(self.history).completed, 1)
        self.assertEqual(source.read_bytes(), b"original")

    def test_undo_refuses_changed_destination_even_with_same_size_and_mtime(self):
        self.file("notes.txt", b"original")
        execute(preview(self.root), self.history)
        dest = self.root / "文档" / "notes.txt"
        stamp = dest.stat()
        dest.write_bytes(b"modified")
        os.utime(dest, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        result = undo(self.history)
        self.assertEqual(result.completed, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(dest.read_bytes(), b"modified")

    def test_new_batch_refused_until_previous_batch_undone(self):
        self.file("first.txt")
        execute(preview(self.root), self.history)
        self.file("second.txt")
        with self.assertRaisesRegex(ValueError, "撤销"):
            execute(preview(self.root), self.history)
        self.assertTrue((self.root / "second.txt").exists())

    def test_pending_move_recovered_after_restart(self):
        self.file("notes.txt")
        execute(preview(self.root), self.history)
        path = self.history / "last-operation.json"
        journal = json.loads(path.read_text(encoding="utf-8"))
        journal["moves"][0]["state"] = "pending"
        path.write_text(json.dumps(journal), encoding="utf-8")
        self.assertEqual(undo(self.history).completed, 1)
        self.assertEqual((self.root / "notes.txt").read_bytes(), b"original")

    def test_malformed_history_does_not_move_anything(self):
        self.history.mkdir()
        (self.history / "last-operation.json").write_text("broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "记录"):
            undo(self.history)

    def test_journal_path_traversal_is_rejected(self):
        self.file("notes.txt")
        execute(preview(self.root), self.history)
        path = self.history / "last-operation.json"
        journal = json.loads(path.read_text(encoding="utf-8"))
        journal["moves"][0]["name"] = "../outside.txt"
        path.write_text(json.dumps(journal), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "记录"):
            undo(self.history)
        self.assertTrue((self.root / "文档" / "notes.txt").exists())

    def test_symlinked_source_and_category_are_not_followed(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "real.txt").write_bytes(b"outside")
        try:
            (self.root / "link.txt").symlink_to(outside / "real.txt")
            (self.root / "文档").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symbolic links requires system permission")
        self.file("notes.txt")
        plan = preview(self.root)
        self.assertNotIn("link.txt", [i.source.name for i in plan.items])
        result = execute(plan, self.history)
        self.assertEqual(result.completed, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse((outside / "notes.txt").exists())

    def test_missing_folder_rejected(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            preview(self.root / "missing")

    def test_keep_results_allows_next_batch_without_moving_previous_files(self):
        self.file("first.txt")
        execute(preview(self.root), self.history)
        forget_history(self.history)
        self.assertFalse(has_history(self.history))
        self.assertEqual((self.root / "文档" / "first.txt").read_bytes(), b"original")
        self.file("second.txt")
        self.assertEqual(execute(preview(self.root), self.history).completed, 1)

    def test_crash_during_undo_can_resume(self):
        self.file("notes.txt")
        execute(preview(self.root), self.history)
        path = self.history / "last-operation.json"
        journal = json.loads(path.read_text(encoding="utf-8"))
        journal["moves"][0]["state"] = "restoring"
        path.write_text(json.dumps(journal), encoding="utf-8")
        (self.root / "文档" / "notes.txt").rename(self.root / "notes.txt")
        self.assertTrue(has_history(self.history))
        result = undo(self.history)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.completed, 1)
        self.assertFalse(has_history(self.history))

    @unittest.skipIf(os.name == "nt", "POSIX hard-link interruption path only")
    def test_crash_between_link_and_unlink_can_resume(self):
        self.file("notes.txt")
        execute(preview(self.root), self.history)
        path = self.history / "last-operation.json"
        journal = json.loads(path.read_text(encoding="utf-8"))
        journal["moves"][0]["state"] = "pending"
        path.write_text(json.dumps(journal), encoding="utf-8")
        os.link(self.root / "文档" / "notes.txt", self.root / "notes.txt")
        result = undo(self.history)
        self.assertEqual(result.completed, 1)
        self.assertFalse((self.root / "文档" / "notes.txt").exists())

    def test_partial_undo_preserves_other_conflicts_for_retry(self):
        self.file("one.txt")
        self.file("two.txt")
        execute(preview(self.root), self.history)
        self.file("one.txt", b"conflict")
        result = undo(self.history)
        self.assertEqual(result.completed, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertTrue((self.root / "two.txt").exists())
        (self.root / "one.txt").unlink()
        self.assertEqual(undo(self.history).completed, 1)

    def test_missing_source_does_not_prevent_other_files_moving(self):
        first = self.file("first.txt")
        self.file("second.txt")
        plan = preview(self.root)
        first.unlink()
        result = execute(plan, self.history)
        self.assertEqual(result.completed, 1)
        self.assertEqual(len(result.errors), 1)

    def test_category_file_reports_error_without_overwriting(self):
        self.file("notes.txt")
        plan = preview(self.root)
        self.file("文档", b"not a folder")
        result = execute(plan, self.history)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual((self.root / "文档").read_bytes(), b"not a folder")
        self.assertTrue((self.root / "notes.txt").exists())

    def test_stale_acceptance_cannot_delete_newer_history(self):
        self.file("first.txt")
        execute(preview(self.root), self.history)
        old_token = history_token(self.history)
        undo(self.history)
        forget_history(self.history)
        self.file("second.txt")
        execute(preview(self.root), self.history)
        new_token = history_token(self.history)
        with self.assertRaisesRegex(ValueError, "更新"):
            forget_history(self.history, expected_token=old_token)
        self.assertEqual(history_token(self.history), new_token)
        self.assertTrue(has_history(self.history))

    def test_repeated_identical_batches_have_distinct_tokens(self):
        self.file("notes.txt")
        execute(preview(self.root), self.history)
        first = history_token(self.history)
        undo(self.history)
        forget_history(self.history)
        execute(preview(self.root), self.history)
        self.assertNotEqual(history_token(self.history), first)

    def test_stale_undo_cannot_affect_newer_batch(self):
        self.file("first.txt")
        execute(preview(self.root), self.history)
        token = history_token(self.history)
        forget_history(self.history)
        self.file("second.txt")
        execute(preview(self.root), self.history)
        with self.assertRaisesRegex(ValueError, "更新"):
            undo(self.history, expected_token=token)
        self.assertFalse((self.root / "second.txt").exists())
        self.assertEqual((self.root / "文档" / "second.txt").read_bytes(), b"original")

    def test_equal_size_source_edit_with_restored_mtime_is_detected(self):
        source = self.file("notes.txt", b"original")
        plan = preview(self.root)
        stamp = source.stat()
        source.write_bytes(b"modified")
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        # Windows 3.12 ctime is creation time; emulate that metadata behavior
        # on POSIX so this regression exercises the content check everywhere.
        from dataclasses import replace
        from organizer.core import _signature
        plan = replace(plan, items=(replace(plan.items[0], signature=_signature(source)),))
        result = execute(plan, self.history)
        self.assertEqual(result.completed, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(source.read_bytes(), b"modified")

    def test_interrupted_undo_recovers_when_category_has_been_removed(self):
        self.file("notes.txt")
        execute(preview(self.root), self.history)
        path = self.history / "last-operation.json"
        journal = json.loads(path.read_text(encoding="utf-8"))
        journal["moves"][0]["state"] = "restoring"
        path.write_text(json.dumps(journal), encoding="utf-8")
        (self.root / "文档" / "notes.txt").rename(self.root / "notes.txt")
        (self.root / "文档").rmdir()
        result = undo(self.history)
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.errors, [])
        self.assertFalse(has_history(self.history))


if __name__ == "__main__":
    unittest.main()
