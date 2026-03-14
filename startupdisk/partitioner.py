"""分区与格式化模块"""

import subprocess
from pathlib import Path


def create_gpt_ntfs_partition(device: str, uefi_ntfs_img_path: Path) -> tuple[str, str]:
    """
    创建 GPT 分区表：
    - 分区1: NTFS，主数据区（留出末尾约 2MB 给 UEFI:NTFS）
    - 分区2: UEFI:NTFS 引导镜像（约 1MB）
    
    返回 (ntfs_partition, efi_partition)，如 ("/dev/sdb1", "/dev/sdb2")
    """
    # 先擦除分区表
    subprocess.run(
        ["wipefs", "-a", device],
        check=True,
        capture_output=True,
    )
    
    # 获取 uefi-ntfs 镜像大小（扇区，512 字节/扇区）
    img_size = uefi_ntfs_img_path.stat().st_size
    img_sectors = (img_size + 511) // 512
    # 预留至少 2MB 给 EFI 分区
    efi_part_size_mb = max(2, (img_sectors * 512) // (1024 * 1024) + 1)
    
    # parted 创建分区
    # 分区1: 从 1MiB 开始，到末尾预留 efi_part_size_mb
    # 分区2: 剩余空间（用于 UEFI:NTFS 引导）
    subprocess.run(["parted", "-s", device, "mklabel", "gpt"], check=True, capture_output=True)
    subprocess.run(
        ["parted", "-s", device, "unit", "MiB", "mkpart", "primary", "ntfs", "1", f"-{efi_part_size_mb}"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["parted", "-s", device, "mkpart", "primary", "fat32", f"-{efi_part_size_mb}", "100%"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["parted", "-s", device, "set", "2", "boot", "on"], check=True, capture_output=True)
    
    # 分区命名约定
    base = Path(device).name
    if base.startswith("nvme"):
        ntfs_part = f"{device}p1"
        efi_part = f"{device}p2"
    else:
        ntfs_part = f"{device}1"
        efi_part = f"{device}2"
    
    # 等待 udev 创建设备节点
    subprocess.run(["udevadm", "settle"], capture_output=True, timeout=5)
    
    # 格式化 NTFS
    subprocess.run(
        ["mkfs.ntfs", "-f", "-L", "WININSTALL", ntfs_part],
        check=True,
        capture_output=True,
    )
    
    return ntfs_part, efi_part


def write_uefi_ntfs_to_partition(uefi_ntfs_img_path: Path, efi_partition: str) -> None:
    """将 UEFI:NTFS 镜像写入 EFI 分区"""
    subprocess.run(
        ["dd", f"if={uefi_ntfs_img_path}", f"of={efi_partition}", "bs=64K", "conv=fsync"],
        check=True,
        capture_output=True,
    )
