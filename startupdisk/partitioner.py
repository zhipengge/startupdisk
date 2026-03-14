"""分区与格式化模块"""

import subprocess
from pathlib import Path


def _get_disk_size_mib(device: str) -> int:
    """获取磁盘总大小（MiB）"""
    result = subprocess.run(
        ["parted", "-s", device, "unit", "MiB", "print"],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.split("\n"):
        if line.startswith("Disk") and ":" in line:
            # Disk /dev/sdb: 59617MiB
            parts = line.split(":")
            if len(parts) >= 2:
                size_str = parts[-1].strip().replace("MiB", "").strip()
                return int(float(size_str))
    raise RuntimeError("无法获取磁盘大小")


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
    
    # 获取 uefi-ntfs 镜像大小
    img_size = uefi_ntfs_img_path.stat().st_size
    # 预留至少 2MiB 给 EFI 分区
    efi_part_size_mb = max(2, (img_size + 1024 * 1024 - 1) // (1024 * 1024) + 1)
    
    # 先创建空的 gpt 表以获取磁盘大小
    subprocess.run(["parted", "-s", device, "mklabel", "gpt"], check=True, capture_output=True)
    disk_size_mib = _get_disk_size_mib(device)
    ntfs_end_mib = disk_size_mib - efi_part_size_mb
    if ntfs_end_mib < 2:
        raise RuntimeError(f"磁盘过小: {disk_size_mib} MiB")
    
    # parted 创建分区（用 -- 避免负值被当作选项）
    # 分区1: 1 MiB 到 ntfs_end_mib
    # 分区2: ntfs_end_mib 到末尾
    subprocess.run(
        ["parted", "-s", device, "unit", "MiB", "mkpart", "primary", "ntfs", "1", str(ntfs_end_mib)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["parted", "-s", device, "unit", "MiB", "mkpart", "primary", "fat32", str(ntfs_end_mib), "100%"],
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
