"""ISO 挂载与文件复制模块"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


class CopyCancelled(Exception):
    """用户强制停止复制"""


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


# 分块大小：4MB 平衡 USB 写入效率与进度更新频率
_COPY_CHUNK = 4 * 1024 * 1024

# >= 此大小的文件使用分块+fdatasync复制（与 _COPY_CHUNK 对齐）
_LARGE_FILE_THRESHOLD = _COPY_CHUNK

# 小文件批量累积到此大小时做一次 os.sync，避免每文件都 fdatasync 的开销
_SMALL_FILE_SYNC_INTERVAL = 64 * 1024 * 1024


def _copy_file_with_progress(
    src_file: Path,
    dst_file: Path,
    bytes_before: int,
    progress_callback,  # (bytes_copied_total: int) -> None
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    """
    分块复制大文件，每块 fdatasync 后报告进度。

    关键设计：
      f.write() 只写入 OS page cache（内存），不代表数据已到 USB。
      调用 fdatasync 强制等待该块真正刷入物理介质后再更新进度，
      使进度条反映真实 USB 写入速度，而非内存写入速度。

      总耗时不变（USB 始终是瓶颈），只是把"瞬间写完+末尾长等"
      变成"匀速写入+进度准确"。
    """
    size = src_file.stat().st_size
    copied = 0
    with open(src_file, "rb") as f_in, open(dst_file, "wb") as f_out:
        while copied < size:
            chunk = min(_COPY_CHUNK, size - copied)
            f_out.write(f_in.read(chunk))
            copied += chunk
            if cancel_check and cancel_check():
                raise CopyCancelled("用户强制停止")
            # fdatasync：确保本块数据物理写入 USB 后再报告
            try:
                os.fdatasync(f_out.fileno())
            except OSError:
                pass
            if progress_callback:
                progress_callback(bytes_before + copied)
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
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    """
    将 ISO 内容复制到 U 盘
    progress_callback(current, total, name, bytes_copied, total_bytes) 进度回调
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
            progress_callback(i, total, name, bc, tb)

    if progress_callback and total > 0:
        _report(0, "", 0, total_bytes)

    small_bytes_since_sync = 0  # 累积的小文件字节数，用于批量 sync

    for i, (src_file, dst_file) in enumerate(all_files):
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        rel_name = str(src_file.relative_to(src))
        file_size = src_file.stat().st_size

        if file_size > 100 * 1024 * 1024:
            _log(f"  正在复制: {rel_name} ({_fmt_size(file_size)})")

        if file_size >= _LARGE_FILE_THRESHOLD:
            # 大文件：分块复制，每块 fdatasync 后报告实际写入进度
            def _byte_cb(bc: int, _i=i, _name=rel_name):
                _report(_i, _name, bc, total_bytes)

            _copy_file_with_progress(
                src_file, dst_file, bytes_copied, _byte_cb, cancel_check
            )
        else:
            # 小文件：shutil.copy2（高效批量）；积累到 _SMALL_FILE_SYNC_INTERVAL 后统一 sync
            if cancel_check and cancel_check():
                raise CopyCancelled("用户强制停止")
            shutil.copy2(src_file, dst_file)
            small_bytes_since_sync += file_size

            if small_bytes_since_sync >= _SMALL_FILE_SYNC_INTERVAL:
                # 批量刷一次，使已报告的小文件进度有实际意义
                try:
                    os.sync()
                except OSError:
                    pass
                small_bytes_since_sync = 0

        bytes_copied += file_size
        _report(i + 1, rel_name, bytes_copied, total_bytes)

    # 最终同步：确保文件系统元数据（目录项、inode）也落盘
    try:
        os.sync()
    except OSError:
        pass

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
