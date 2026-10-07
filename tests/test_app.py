import os
import gc
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from organizer.app import OrganizerApp, default_history_dir, downloads_folder


@unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"), "A real display is required for GUI integration tests")
class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "下载"
        self.folder.mkdir()
        self.history = Path(self.temp.name) / "history"
        self.root = tk.Tk()
        self.addCleanup(self.cleanup_window)
        self.app = OrganizerApp(self.root, self.folder, self.history)
        self.root.update()

    def cleanup_window(self):
        self.root.destroy()
        self.app = None
        self.root = None
        # Tk interpreters must be released on their creating thread. A restart
        # in real use is a new process; this suite reuses one test process.
        gc.collect()

    def wait(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertFalse(self.app.busy, "Background operation did not finish")

    def test_preview_organize_restart_undo_real_files(self):
        (self.folder / "学习笔记.txt").write_bytes(b"notes")
        (self.folder / "照片.png").write_bytes(b"picture")
        self.app.on_preview()
        self.wait()
        self.assertEqual(len(self.app.tree.get_children()), 2)
        self.assertTrue((self.folder / "学习笔记.txt").exists())
        with patch("organizer.app.messagebox.askyesno", return_value=True):
            self.app.on_organize()
        self.wait()
        self.assertEqual(self.app.last_result.completed, 2)
        self.assertEqual((self.folder / "文档" / "学习笔记.txt").read_bytes(), b"notes")
        self.assertFalse(self.app.undo_button.instate(["disabled"]))
        # Recreate the window to verify persistent startup history and undo.
        self.root.destroy()
        self.app = None
        self.root = None
        gc.collect()
        self.root = tk.Tk()
        self.app = OrganizerApp(self.root, self.folder, self.history)
        self.assertFalse(self.app.undo_button.instate(["disabled"]))
        with patch("organizer.app.messagebox.askyesno", return_value=True):
            self.app.on_undo()
        self.wait()
        self.assertEqual(self.app.last_result.completed, 2)
        self.assertEqual((self.folder / "学习笔记.txt").read_bytes(), b"notes")
        self.assertTrue(self.app.undo_button.instate(["disabled"]))

    def test_cancel_confirmation_does_not_move_files(self):
        (self.folder / "notes.txt").write_bytes(b"notes")
        self.app.on_preview()
        self.wait()
        with patch("organizer.app.messagebox.askyesno", return_value=False):
            self.app.on_organize()
        self.assertFalse(self.app.busy)
        self.assertTrue((self.folder / "notes.txt").exists())

    def test_invalid_folder_error_is_visible_and_app_stays_usable(self):
        self.app.folder.set(str(self.folder / "missing"))
        self.app.on_preview()
        self.wait()
        self.assertIn("失败", self.app.status.get())
        self.assertIn("missing", self.app.log.get("1.0", "end"))
        self.assertFalse(self.app.preview_button.instate(["disabled"]))

    def test_empty_preview_disables_organize(self):
        self.app.on_preview()
        self.wait()
        self.assertTrue(self.app.organize_button.instate(["disabled"]))
        self.assertIn("0", self.app.summary.get())

    def test_footer_is_visible_at_default_window_size(self):
        self.root.update_idletasks()
        footer_bottom = self.app.log.winfo_rooty() + self.app.log.winfo_height()
        window_bottom = self.root.winfo_rooty() + self.root.winfo_height()
        self.assertLessEqual(footer_bottom, window_bottom)
        self.assertTrue(self.app.log.winfo_ismapped())

    def test_undo_conflict_shown_and_retry_remains_available(self):
        source = self.folder / "notes.txt"
        source.write_bytes(b"original")
        self.app.on_preview()
        self.wait()
        with patch("organizer.app.messagebox.askyesno", return_value=True):
            self.app.on_organize()
            self.wait()
            source.write_bytes(b"conflict")
            self.app.on_undo()
            self.wait()
        self.assertEqual(source.read_bytes(), b"conflict")
        self.assertEqual(len(self.app.last_result.errors), 1)
        self.assertIn("未覆盖", self.app.log.get("1.0", "end"))
        self.assertFalse(self.app.undo_button.instate(["disabled"]))

    def test_stale_window_cannot_clear_other_windows_new_batch(self):
        from organizer.core import execute, forget_history, has_history, preview
        (self.folder / "first.txt").write_bytes(b"first")
        self.app.on_preview()
        self.wait()
        with patch("organizer.app.messagebox.askyesno", return_value=True):
            self.app.on_organize()
        self.wait()
        forget_history(self.history)
        (self.folder / "second.txt").write_bytes(b"second")
        execute(preview(self.folder), self.history)
        with patch("organizer.app.messagebox.askyesno", return_value=True):
            self.app.on_keep()
        self.wait()
        self.assertTrue(has_history(self.history))
        self.assertIn("更新", self.app.log.get("1.0", "end"))


class DefaultsTests(unittest.TestCase):
    def test_history_directory_is_separate_from_downloads(self):
        self.assertNotEqual(default_history_dir(), downloads_folder())
        self.assertEqual(default_history_dir().name, "DownloadOrganizer")


if __name__ == "__main__":
    unittest.main()
