"""ISO 挂载与文件复制模块"""

import shutil
import subprocess
import tempfile
from pathlib import Path


def mount_iso(iso_path: str) -> str:
    """挂载 ISO 到临时目录，返回挂载点路径"""
    mount_point = tempfile.mkdtemp(prefix="startupdisk_iso_")
    subprocess.run(
        ["mount", "-o", "ro,loop", iso_path, mount_point],
        check=True,
        capture_output=True,
    )
    return mount_point


def unmount_iso(mount_point: str) -> None:
    """卸载 ISO"""
    subprocess.run(["umount", mount_point], check=True, capture_output=True)
    Path(mount_point).rmdir()


_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB


def _copy_file_with_progress(
    src_file: Path,
    dst_file: Path,
    bytes_before: int,
    total_bytes: int,
    progress_callback,  # (bytes_copied_total: int) -> None
) -> None:
    """大文件分块复制，支持字节进度回调"""
    size = src_file.stat().st_size
    report_interval = 2 * 1024 * 1024  # 每 2MB 报告一次，保证进度条实时
    copied = 0
    with open(src_file, "rb") as f_in, open(dst_file, "wb") as f_out:
        while copied < size:
            chunk = min(_CHUNK_SIZE, size - copied)
            f_out.write(f_in.read(chunk))
            copied += chunk
            if progress_callback and (copied % report_interval < _CHUNK_SIZE or copied >= size):
                progress_callback(bytes_before + copied)
    # 保留元数据
    shutil.copystat(src_file, dst_file)


def _fmt_size(b: int) -> str:
    """格式化字节为可读单位"""
    if b >= 1024 * 1024 * 1024:
        return f"{b / (1024**3):.1f} GB"
    return f"{b / (1024 * 1024):.1f} MB"


def copy_iso_to_usb(
    iso_mount_point: str,
    usb_mount_point: str,
    progress_callback=None,
    log_callback=None,
) -> None:
    """
    将 ISO 内容复制到 U 盘
    progress_callback(current, total, name, bytes_copied=0, total_bytes=0) 可选进度回调
    log_callback(msg) 可选日志回调，输出具体刷写日志
    """
    src = Path(iso_mount_point)
    dst = Path(usb_mount_point)

    all_files: list[tuple[Path, Path]] = []
    for f in src.rglob("*"):
        if f.is_file():
            rel = f.relative_to(src)
            all_files.append((f, dst / rel))

    total = len(all_files)
    total_bytes = sum(f.stat().st_size for f, _ in all_files)
    bytes_copied = 0

    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    def _report(i: int, name: str, bc: int, tb: int):
        if progress_callback:
            try:
                progress_callback(i, total, name, bc, tb)
            except TypeError:
                progress_callback(i, total, name)

    for i, (src_file, dst_file) in enumerate(all_files):
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        rel_name = str(src_file.relative_to(src))
        file_size = src_file.stat().st_size
        # 复制前报告
        if i % 10 == 0 or i == total - 1 or file_size > 100 * 1024 * 1024:
            _report(i, rel_name, bytes_copied, total_bytes)
        # 大文件开始前写入日志
        if file_size > 100 * 1024 * 1024:
            _log(f"  正在复制: {rel_name} ({_fmt_size(file_size)})")
        # 大文件(>20MB)分块复制以获取实时进度
        if file_size > 20 * 1024 * 1024:
            def _byte_cb(bc: int):
                _report(i, rel_name, bc, total_bytes)
            _copy_file_with_progress(src_file, dst_file, bytes_copied, total_bytes, _byte_cb)
        else:
            shutil.copy2(src_file, dst_file)
        bytes_copied += file_size
    if progress_callback and total > 0:
        progress_callback(total, total, "", bytes_copied, total_bytes)


def mount_partition(partition: str) -> str:
    """挂载分区到临时目录"""
    mount_point = tempfile.mkdtemp(prefix="startupdisk_usb_")
    subprocess.run(
        ["mount", partition, mount_point],
        check=True,
        capture_output=True,
    )
    return mount_point


def unmount_partition(mount_point: str) -> None:
    """卸载分区"""
    subprocess.run(["umount", mount_point], check=True, capture_output=True)
    Path(mount_point).rmdir()
