"""Run the desktop application, or perform a short real-window smoke check."""

import argparse
import ctypes
import os
import sys
import tkinter as tk

from organizer.app import OrganizerApp


def main() -> int:
    parser = argparse.ArgumentParser(description="下载整理助手")
    parser.add_argument("--smoke-test", action="store_true", help="打开实际窗口并自动退出，用于验证打包结果")
    args = parser.parse_args()
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    try:
        root = tk.Tk()
        app = OrganizerApp(root)
        if args.smoke_test:
            root.update()
            assert app.preview_button.winfo_exists()
            root.after(300, root.destroy)
        root.mainloop()
    except Exception as exc:
        print(f"无法启动下载整理助手：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
