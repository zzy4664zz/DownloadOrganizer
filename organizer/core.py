"""Plan-only previews, non-overwriting moves, and durable single-batch undo.

The selected folder and its category directories must not be modified by other
programs during a move. No directory traversal or recursive organizing occurs.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid
from typing import Callable


CATEGORIES = {
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".heic", ".tif", ".tiff", ".avif"},
    "文档": {".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md", ".rtf", ".odt", ".epub"},
    "视频": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "音频": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"},
    "安装包": {".exe", ".msi", ".msix", ".appx", ".apk", ".dmg", ".deb", ".rpm", ".iso"},
    "其他": set(),
}
TEMP_SUFFIXES = {".part", ".partial", ".crdownload", ".download", ".tmp", ".temp", ".opdownload"}
JOURNAL = "last-operation.json"
Progress = Callable[[int, int, str], None]


@dataclass(frozen=True)
class Move:
    source: Path
    destination: Path
    signature: tuple
    sha256: str


@dataclass(frozen=True)
class Plan:
    folder: Path
    items: tuple[Move, ...]
    skipped: int = 0


@dataclass
class Result:
    completed: int = 0
    errors: list[str] = field(default_factory=list)


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400  # Windows reparse point
    )


def _signature(path: Path) -> tuple:
    info = path.lstat()
    if _is_link(path) or not stat.S_ISREG(info.st_mode):
        raise ValueError("文件不是普通文件，或是链接")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _category(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return next((name for name, extensions in CATEGORIES.items() if suffix in extensions), "其他")


def _available(directory: Path, name: str, reserved: set[str] | None = None) -> Path:
    occupied = set(reserved or ())
    # Case-fold names on every platform so previews model Windows collisions.
    if directory.is_dir() and not _is_link(directory):
        occupied.update(item.name.casefold() for item in directory.iterdir())
    candidate = name
    count = 0
    original = Path(name)
    while candidate.casefold() in occupied or os.path.lexists(directory / candidate):
        count += 1
        candidate = f"{original.stem} ({count}){original.suffix}"
    if reserved is not None:
        reserved.add(candidate.casefold())
    return directory / candidate


def preview(folder: Path) -> Plan:
    """Read direct children without creating directories or moving files."""
    folder = Path(folder).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("请选择一个文件夹")
    moves = []
    skipped = 0
    reserved: dict[str, set[str]] = {}
    for source in sorted(folder.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
        info = source.lstat()
        hidden = source.name.startswith(".") or bool(getattr(info, "st_file_attributes", 0) & 2)
        if hidden or _is_link(source) or not stat.S_ISREG(info.st_mode) or source.suffix.lower() in TEMP_SUFFIXES:
            skipped += 1
            continue
        category = _category(source.name)
        destination = _available(folder / category, source.name, reserved.setdefault(category, set()))
        signature = _signature(source)
        checksum = _digest(source)
        if _signature(source) != signature:
            raise ValueError(f"文件正在变化，请等待下载或编辑完成后再预览：{source.name}")
        moves.append(Move(source, destination, signature, checksum))
    return Plan(folder, tuple(moves), skipped)


@contextmanager
def _lock(history: Path):
    history.mkdir(parents=True, exist_ok=True)
    with (history / ".operation.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("另一个整理助手正在操作，请稍后重试") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _write(history: Path, journal: dict):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=history, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(journal, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, history / JOURNAL)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _basename(value) -> bool:
    return isinstance(value, str) and bool(value) and value not in {".", ".."} and not any(
        char in value for char in ("/", "\\", "\x00", ":")
    )


def _read(history: Path) -> dict | None:
    path = history / JOURNAL
    if not path.exists():
        return None
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
        if journal["version"] != 1 or not isinstance(journal["moves"], list):
            raise ValueError()
        if not isinstance(journal["folder"], str) or not Path(journal["folder"]).is_absolute():
            raise ValueError()
        for move in journal["moves"]:
            if not _basename(move["name"]) or not _basename(move["destination"]):
                raise ValueError()
            if move["category"] not in CATEGORIES or move["state"] not in {"pending", "moved", "restoring", "undone", "failed"}:
                raise ValueError()
            if not isinstance(move["sha256"], str) or len(move["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in move["sha256"]):
                raise ValueError()
        return journal
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("整理记录损坏或格式不正确，请保留记录并检查文件位置") from exc


def has_history(history: Path) -> bool:
    """Whether a batch has unfinished undo records; invalid history raises."""
    journal = _read(Path(history))
    return bool(journal and any(m["state"] in {"pending", "moved", "restoring"} for m in journal["moves"]))


def history_token(history: Path) -> str | None:
    """Snapshot revision, including invalid journals that a user may clear."""
    try:
        return _digest(Path(history) / JOURNAL)
    except FileNotFoundError:
        return None


def _check_token(history: Path, expected_token: str | None):
    if expected_token is not None and history_token(history) != expected_token:
        raise ValueError("撤销记录已被其他窗口更新，请核对最新记录后重试")


def forget_history(history: Path, *, expected_token: str | None = None):
    """Explicitly accept the last batch; this does not change organized files."""
    history = Path(history)
    with _lock(history):
        _check_token(history, expected_token)
        (history / JOURNAL).unlink(missing_ok=True)


def _directory(path: Path, create: bool = False):
    if create:
        path.mkdir(exist_ok=True)
    if not path.is_dir() or _is_link(path):
        raise ValueError(f"分类目录不可用或是链接：{path.name}")


def _move(source: Path, destination: Path):
    """Never overwrite: Windows rename is exclusive; POSIX uses link/unlink.

    POSIX interruption can leave both hard links. The pending journal allows
    undo to recognize that case. No fallback to an overwriting shutil.move.
    """
    if os.name == "nt":
        os.rename(source, destination)
    else:
        os.link(source, destination, follow_symlinks=False)
        source.unlink()


def execute(plan: Plan, history: Path, progress: Progress | None = None) -> Result:
    """Revalidate the preview and persist intent before each exclusive move."""
    history = Path(history)
    result = Result()
    with _lock(history):
        if has_history(history):
            raise ValueError("请先撤销上次整理，或选择保留结果并清除撤销记录")
        _directory(plan.folder)
        journal = {"version": 1, "batch": uuid.uuid4().hex, "folder": str(plan.folder), "moves": []}
        for index, item in enumerate(plan.items, 1):
            record = None
            try:
                if item.source.parent != plan.folder or item.destination.parent.parent != plan.folder or item.destination.parent.name not in CATEGORIES:
                    raise ValueError("预览路径不合法，请重新预览")
                if _signature(item.source) != item.signature:
                    raise ValueError("文件在预览后已更改，请重新预览")
                checksum = _digest(item.source)
                if _signature(item.source) != item.signature or checksum != item.sha256:
                    raise ValueError("文件在检查时已更改，请重新预览")
                _directory(item.destination.parent, create=True)
                destination = _available(item.destination.parent, item.source.name)
                record = {"name": item.source.name, "category": destination.parent.name,
                          "destination": destination.name, "sha256": checksum, "state": "pending"}
                journal["moves"].append(record)
                _write(history, journal)
                _move(item.source, destination)
            except (OSError, ValueError) as exc:
                result.errors.append(f"{item.source.name}：{exc}")
                # Keep pending intent on an uncertain move; undo inspects paths.
                if record is not None:
                    _write(history, journal)
            else:
                record["state"] = "moved"
                _write(history, journal)
                result.completed += 1
            if progress:
                progress(index, len(plan.items), item.source.name)
    return result


def undo(history: Path, progress: Progress | None = None, *, expected_token: str | None = None) -> Result:
    """Restore only unchanged files; retain unresolved conflicts for retry."""
    history = Path(history)
    result = Result()
    with _lock(history):
        _check_token(history, expected_token)
        journal = _read(history)
        if journal is None:
            return result
        folder = Path(journal["folder"])
        _directory(folder)
        moves = [m for m in reversed(journal["moves"]) if m["state"] in {"pending", "moved", "restoring"}]
        for index, record in enumerate(moves, 1):
            source = folder / record["name"]
            destination = folder / record["category"] / record["destination"]
            try:
                if not os.path.lexists(destination) and record["state"] in {"pending", "restoring"} and os.path.lexists(source):
                    signature = _signature(source)
                    if _digest(source) != record["sha256"] or _signature(source) != signature:
                        raise ValueError("原文件已更改，无法确认未完成操作")
                else:
                    _directory(destination.parent)
                    signature = _signature(destination)
                    if _digest(destination) != record["sha256"] or _signature(destination) != signature:
                        raise ValueError("整理后的文件已更改，已跳过")
                    if os.path.lexists(source):
                        if record["state"] in {"pending", "restoring"} and not _is_link(source) and os.path.samefile(source, destination):
                            destination.unlink()
                        else:
                            raise ValueError("原位置已有文件，未覆盖；移走冲突文件后可重试")
                    else:
                        record["state"] = "restoring"
                        _write(history, journal)
                        _move(destination, source)
            except (OSError, ValueError) as exc:
                result.errors.append(f"{record['name']}：{exc}")
            else:
                record["state"] = "undone"
                _write(history, journal)
                result.completed += 1
            if progress:
                progress(index, len(moves), record["name"])
    return result
