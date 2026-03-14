"""启动盘创建核心逻辑，供 CLI 和 GUI 共用"""

from pathlib import Path
from typing import Callable

from .device_detector import get_usb_devices, is_device_mounted
from .partitioner import create_gpt_ntfs_partition, write_uefi_ntfs_to_partition
from .uefi_ntfs import get_uefi_ntfs_path
from .writer import copy_iso_to_usb, mount_iso, mount_partition, unmount_iso, unmount_partition


def create_startup_disk(
    iso_path: str | Path,
    device: str,
    uefi_ntfs_path: str | Path | None = None,
    *,
    log_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    """
    制作 Windows 启动盘
    
    Args:
        iso_path: Windows ISO 文件路径
        device: 目标 USB 设备，如 /dev/sdb
        uefi_ntfs_path: UEFI:NTFS 镜像路径，None 则自动下载
        log_callback: 日志回调 (message) -> None
        progress_callback: 复制进度回调 (current, total, name) -> None
    """
    iso_path = Path(iso_path)
    device = device if device.startswith("/dev/") else f"/dev/{device}"

    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    iso_mount = None
    usb_mount = None

    try:
        log("正在准备 UEFI:NTFS 引导镜像...")
        uefi_ntfs = get_uefi_ntfs_path(str(uefi_ntfs_path) if uefi_ntfs_path else None)
        log(f"  使用: {uefi_ntfs}")

        log("正在创建分区...")
        ntfs_part, efi_part = create_gpt_ntfs_partition(device, uefi_ntfs)
        log(f"  NTFS 分区: {ntfs_part}")
        log(f"  EFI 分区: {efi_part}")

        log("正在写入 UEFI:NTFS 引导...")
        write_uefi_ntfs_to_partition(uefi_ntfs, efi_part)

        log("正在挂载 ISO...")
        iso_mount = mount_iso(str(iso_path))

        log("正在挂载 U 盘...")
        usb_mount = mount_partition(ntfs_part)

        log("正在复制文件（可能需要几分钟）...")
        copy_iso_to_usb(
            iso_mount,
            usb_mount,
            progress_callback=progress_callback,
            log_callback=log,
        )
        log("复制完成。")

        log("正在卸载...")
        unmount_partition(usb_mount)
        usb_mount = None
        unmount_iso(iso_mount)
        iso_mount = None

        log("完成！Windows 启动盘已制作成功。")
        log("请安全弹出 U 盘后用于启动安装。")

    finally:
        if usb_mount:
            try:
                unmount_partition(usb_mount)
            except Exception:
                pass
        if iso_mount:
            try:
                unmount_iso(iso_mount)
            except Exception:
                pass
