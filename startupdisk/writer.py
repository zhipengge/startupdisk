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


def copy_iso_to_usb(iso_mount_point: str, usb_mount_point: str, progress_callback=None) -> None:
    """
    将 ISO 内容复制到 U 盘
    progress_callback(current, total, name) 可选进度回调
    """
    src = Path(iso_mount_point)
    dst = Path(usb_mount_point)
    
    all_files: list[tuple[Path, Path]] = []
    for f in src.rglob("*"):
        if f.is_file():
            rel = f.relative_to(src)
            all_files.append((f, dst / rel))
    
    total = len(all_files)
    for i, (src_file, dst_file) in enumerate(all_files):
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        if progress_callback and (i % 10 == 0 or i == total - 1):
            progress_callback(i + 1, total, str(src_file.relative_to(src)))


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
