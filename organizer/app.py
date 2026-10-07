"""Chinese desktop UI; workers communicate with Tk only through a queue."""

from collections import Counter
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid

from organizer import __version__
from organizer.core import execute, forget_history, has_history, history_token, preview, undo


def downloads_folder() -> Path:
    """Ask Windows for the real Downloads location (including redirection)."""
    if os.name == "nt":
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        identifier = GUID.from_buffer_copy(uuid.UUID("374de290-123f-4565-9164-39c4925e467b").bytes_le)
        pointer = ctypes.c_void_p()
        shell = ctypes.windll.shell32.SHGetKnownFolderPath
        shell.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        shell.restype = ctypes.c_long
        free = ctypes.windll.ole32.CoTaskMemFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = None
        if shell(ctypes.byref(identifier), 0, None, ctypes.byref(pointer)) == 0:
            try:
                return Path(ctypes.wstring_at(pointer))
            finally:
                free(pointer)
    return Path.home() / "Downloads"


def default_history_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "DownloadOrganizer"


def _size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{value} B"
        amount /= 1024


class OrganizerApp:
    def __init__(self, root: tk.Tk, initial_folder=None, history_dir=None):
        self.root = root
        self.history = Path(history_dir) if history_dir is not None else default_history_dir()
        self.folder = tk.StringVar(root, value=str(initial_folder if initial_folder is not None else downloads_folder()))
        self.status = tk.StringVar(root, value="先预览，再整理。你的文件始终由你决定。")
        self.summary = tk.StringVar(root, value="等待预览")
        self.history_status = tk.StringVar(root)
        self.busy = False
        self.plan = None
        self.last_result = None
        self.pending_history = False
        self.history_revision = None
        self.events = queue.Queue()
        self.worker_thread = None
        self.poll_id = None
        self.closed = False
        self._build()
        self._refresh_history()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Destroy>", self._destroyed, add="+")
        self.poll_id = self.root.after(70, self._poll)

    def _build(self):
        root = self.root
        root.title(f"下载整理助手 · v{__version__}")
        root.geometry("980x730")
        root.minsize(760, 600)
        root.configure(background="#eef3f5")
        font = "Microsoft YaHei UI" if os.name == "nt" else "sans-serif"
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef3f5")
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", font=(font, 10), background="#eef3f5", foreground="#243647")
        style.configure("Card.TLabel", background="white")
        style.configure("Title.TLabel", font=(font, 25, "bold"), foreground="#163b43")
        style.configure("Hint.TLabel", foreground="#617482")
        style.configure("TButton", font=(font, 10), padding=(14, 9))
        style.configure("Primary.TButton", background="#167d72", foreground="white")
        style.map("Primary.TButton", background=[("disabled", "#d7e1e2"), ("active", "#12675e")], foreground=[("disabled", "#71858a")])
        style.configure("Treeview", font=(font, 10), rowheight=32, background="white", fieldbackground="white", borderwidth=0)
        style.configure("Treeview.Heading", font=(font, 10, "bold"), padding=(8, 9), background="#e4eeee", foreground="#304d54")
        style.map("Treeview", background=[("selected", "#d4ebe7")], foreground=[("selected", "#173e40")])
        style.configure("TProgressbar", background="#167d72", troughcolor="#dfebeb", borderwidth=0)

        outer = ttk.Frame(root, padding=(26, 22))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)
        ttk.Label(outer, text="下载整理助手", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="把散落的下载文件，整理成一目了然的分类。", style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 18))

        folder_card = ttk.Frame(outer, style="Card.TFrame", padding=16)
        folder_card.grid(row=2, column=0, sticky="ew")
        ttk.Label(folder_card, text="01  选择要整理的文件夹", style="Card.TLabel").pack(anchor="w", pady=(0, 10))
        folder_row = ttk.Frame(folder_card, style="Card.TFrame")
        folder_row.pack(fill="x")
        self.folder_entry = ttk.Entry(folder_row, textvariable=self.folder, state="readonly", font=(font, 10))
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.browse_button = ttk.Button(folder_row, text="选择文件夹…", command=self.on_browse)
        self.browse_button.pack(side="left", padx=(12, 0))

        heading = ttk.Frame(outer)
        heading.grid(row=3, column=0, sticky="ew", pady=(18, 9))
        ttk.Label(heading, text="02  查看整理预览", font=(font, 11, "bold")).pack(side="left")
        ttk.Label(heading, textvariable=self.summary, style="Hint.TLabel").pack(side="right")
        table = ttk.Frame(outer, style="Card.TFrame")
        table.grid(row=4, column=0, sticky="nsew")
        self.tree = ttk.Treeview(table, columns=("file", "category", "destination", "size"), show="headings", selectmode="browse", height=7)
        for name, label, width in (("file", "文件名", 250), ("category", "分类", 80), ("destination", "整理后的位置", 320), ("size", "大小", 90)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=70, stretch=name in {"file", "destination"}, anchor="e" if name == "size" else "w")
        self.tree.tag_configure("even", background="#f6faf9")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        ttk.Label(outer, text="只整理当前层文件；跳过子文件夹、隐藏文件、链接和未完成下载。重名自动编号。", style="Hint.TLabel", wraplength=700).grid(row=5, column=0, sticky="w", pady=(9, 10))

        actions = ttk.Frame(outer)
        actions.grid(row=6, column=0, sticky="ew")
        self.preview_button = ttk.Button(actions, text="预览分类", command=self.on_preview)
        self.preview_button.pack(side="left")
        self.organize_button = ttk.Button(actions, text="开始整理", style="Primary.TButton", command=self.on_organize)
        self.organize_button.pack(side="left", padx=10)
        self.undo_button = ttk.Button(actions, text="撤销上次整理", command=self.on_undo)
        self.undo_button.pack(side="right")
        self.keep_button = ttk.Button(actions, text="保留结果", command=self.on_keep)
        self.keep_button.pack(side="right", padx=10)
        ttk.Label(outer, textvariable=self.history_status, style="Hint.TLabel", wraplength=700).grid(row=7, column=0, sticky="w", pady=(9, 10))
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(outer, textvariable=self.status, wraplength=700).grid(row=9, column=0, sticky="w")

        log_frame = ttk.Frame(outer)
        log_frame.grid(row=10, column=0, sticky="ew", pady=(8, 0))
        self.log = tk.Text(log_frame, height=3, font=(font, 9), background="#e5edef", foreground="#47616c", relief="flat", padx=10, pady=7, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="x", expand=True)
        log_scroll.pack(side="right", fill="y")
        self._buttons()

    def _buttons(self):
        for button in (self.browse_button, self.preview_button):
            button.state(["disabled" if self.busy else "!disabled"])
        self.organize_button.state(["!disabled" if not self.busy and self.plan and self.plan.items and not self.pending_history else "disabled"])
        for button in (self.undo_button, self.keep_button):
            button.state(["!disabled" if self.pending_history and not self.busy else "disabled"])

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh_history(self):
        try:
            self.history_revision = history_token(self.history)
            self.pending_history = has_history(self.history)
            self.history_status.set("上次整理可撤销；开始下一批前，请先撤销或选择「保留结果」。" if self.pending_history else "撤销记录保存在本机，关闭软件后仍可使用。")
        except (OSError, ValueError) as exc:
            self.pending_history = True
            self.history_status.set("撤销记录无法读取，请查看下方错误详情。")
            self._append(str(exc))
        self._buttons()

    def _clear(self):
        self.plan = None
        self.tree.delete(*self.tree.get_children())
        self._buttons()

    def on_browse(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(parent=self.root, title="选择要整理的文件夹", initialdir=self.folder.get(), mustexist=True)
        if folder:
            self.folder.set(folder)
            self._clear()
            self.summary.set("等待预览")
            self.status.set("文件夹已选择，请点击「预览分类」。")

    def _run(self, action, task):
        if self.busy:
            return
        self.busy = True
        self.progress.configure(value=0, mode="indeterminate")
        self.progress.start(12)
        self.status.set(f"正在{action}，请稍候…")
        self._buttons()
        events = self.events

        def worker():
            try:
                events.put(("done", action, task()))
            except Exception as exc:
                events.put(("error", action, str(exc)))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _report_progress(self, count, total, name):
        self.events.put(("progress", count / max(total, 1) * 100, name))

    def on_preview(self):
        if self.busy:
            return
        self._clear()
        folder = Path(self.folder.get())
        self._run("预览", lambda: preview(folder))

    def on_organize(self):
        if self.busy or not self.plan or not self.plan.items or self.pending_history:
            return
        plan = self.plan
        if messagebox.askyesno("确认整理", f"将整理 {len(plan.items)} 个文件到：\n{plan.folder}\n\n预览会再次检查，重名自动编号。是否继续？", parent=self.root):
            self._run("整理", lambda: execute(plan, self.history, self._report_progress))

    def on_undo(self):
        if self.busy or not self.pending_history:
            return
        revision = self.history_revision
        if messagebox.askyesno("确认撤销", "将恢复上次整理的文件，可能来自其他文件夹。\n\n已修改的文件和原位置冲突会跳过，未解决记录可重试。是否继续？", parent=self.root):
            self._run("撤销", lambda: undo(self.history, self._report_progress, expected_token=revision))

    def on_keep(self):
        if self.busy or not self.pending_history:
            return
        revision = self.history_revision
        if messagebox.askyesno("保留整理结果", "文件会保持现状，但将清除上次的撤销记录。\n清除后无法通过本工具撤销该批整理。\n\n是否保留结果？", parent=self.root):
            self._run("保留结果", lambda: forget_history(self.history, expected_token=revision))

    def _poll(self):
        if self.closed:
            return
        # Bound each poll so progress from very large folders cannot starve Tk.
        for _ in range(200):
            try:
                kind, action, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self.progress.stop()
                self.progress.configure(mode="determinate", value=action)
                self.status.set(f"正在处理：{payload}")
                continue
            # A done event can arrive just before Thread.run releases its task
            # closure. Wait for that release before permitting window teardown.
            self.worker_thread.join()
            self.worker_thread = None
            self.busy = False
            self.progress.stop()
            self.progress.configure(mode="determinate", value=100 if kind == "done" else 0)
            if kind == "error":
                self.status.set(f"{action}失败，请查看错误详情。")
                self._append(f"{action}失败：{payload}")
                self._clear()
            elif action == "预览":
                self.plan = payload
                for index, item in enumerate(payload.items):
                    self.tree.insert("", "end", values=(item.source.name, item.destination.parent.name,
                        str(item.destination.relative_to(payload.folder)), _size(item.signature[2])), tags=("even",) if index % 2 == 0 else ())
                total = sum(item.signature[2] for item in payload.items)
                self.summary.set(f"{len(payload.items)} 个文件 · {_size(total)} · 跳过 {payload.skipped} 项")
                counts = Counter(item.destination.parent.name for item in payload.items)
                self._append("预览完成：" + ("，".join(f"{name} {count} 个" for name, count in counts.items()) or "没有需要整理的文件"))
                self.status.set("预览完成。核对列表后，点击「开始整理」。" if payload.items else "当前文件夹没有需要整理的文件。")
            elif action == "保留结果":
                self.status.set("已保留整理结果，撤销记录已清除。可预览下一批文件。")
                self._append(self.status.get())
            else:
                self.last_result = payload
                self._clear()
                self.summary.set(f"{action}完成 {payload.completed} 个 · 未处理 {len(payload.errors)} 个")
                self.status.set(f"{action}完成：{payload.completed} 个文件。" + (f"另有 {len(payload.errors)} 项未处理，请查看详情。" if payload.errors else ""))
                self._append(self.status.get())
                for error in payload.errors:
                    self._append(error)
            self._refresh_history()
        self.poll_id = self.root.after(70, self._poll)

    def _destroyed(self, event):
        if event.widget is self.root:
            self.closed = True
            if self.poll_id is not None:
                self.root.after_cancel(self.poll_id)

    def on_close(self):
        if self.busy:
            messagebox.showwarning("操作进行中", "请等待当前操作完成后再关闭，以便保存撤销记录。", parent=self.root)
            return
        self.root.destroy()
