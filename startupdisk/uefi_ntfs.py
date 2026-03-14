"""UEFI:NTFS 引导镜像下载与管理"""

import os
import platform
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


UEFI_NTFS_RELEASE_URL = "https://github.com/pbatard/uefi-ntfs/releases/download/v2.7"
CACHE_DIR = Path.home() / ".cache" / "startupdisk"


def _get_arch_config() -> tuple[str, str]:
    """返回 (缓存文件名, EFI 下载文件名)"""
    machine = platform.machine().lower()
    arch_map = {
        "x86_64": ("uefi-ntfs_x64.img", "bootx64.efi"),
        "amd64": ("uefi-ntfs_x64.img", "bootx64.efi"),
        "aarch64": ("uefi-ntfs_arm64.img", "bootaa64.efi"),
        "armv8l": ("uefi-ntfs_arm64.img", "bootaa64.efi"),
        "arm64": ("uefi-ntfs_arm64.img", "bootaa64.efi"),
    }
    return arch_map.get(machine, ("uefi-ntfs_x64.img", "bootx64.efi"))


def _build_img_from_efi(efi_path: Path, img_path: Path) -> None:
    """从 bootx64.efi 构建 FAT 引导镜像"""
    img_size = 1024 * 1024  # 1MB
    img_path.parent.mkdir(parents=True, exist_ok=True)
    with open(img_path, "wb") as f:
        f.truncate(img_size)
    try:
        loop = subprocess.run(
            ["losetup", "-f", "--show", str(img_path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        loop_dev = loop.stdout.strip()
        try:
            subprocess.run(["mkfs.vfat", "-F", "12", "-n", "UEFI_NTFS", loop_dev], check=True, capture_output=True)
            mount_point = tempfile.mkdtemp(prefix="uefi_ntfs_")
            try:
                subprocess.run(["mount", loop_dev, mount_point], check=True, capture_output=True)
                efi_boot = Path(mount_point) / "EFI" / "BOOT"
                efi_boot.mkdir(parents=True, exist_ok=True)
                name_lower = efi_path.name.lower()
                if "aa64" in name_lower:
                    dest = efi_boot / "BOOTAA64.EFI"
                else:
                    dest = efi_boot / "BOOTX64.EFI"
                shutil.copy2(efi_path, dest)
            finally:
                subprocess.run(["umount", mount_point], capture_output=True, timeout=5)
                Path(mount_point).rmdir()
        finally:
            subprocess.run(["losetup", "-d", loop_dev], capture_output=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        img_path.unlink(missing_ok=True)
        raise RuntimeError(f"构建 UEFI:NTFS 镜像失败: {e}") from e


def get_uefi_ntfs_path(custom_path: str | None = None) -> Path:
    """
    获取 uefi-ntfs.img 路径
    优先使用用户指定路径，否则从缓存或下载/构建
    """
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"指定的 UEFI:NTFS 镜像不存在: {custom_path}")

    cache_name, efi_name = _get_arch_config()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / cache_name

    if cached.exists():
        return cached

    ctx = ssl.create_default_context()

    # 1. 尝试下载预构建的 .img（旧版可能有）
    img_url = f"{UEFI_NTFS_RELEASE_URL}/{cache_name}"
    try:
        with urllib.request.urlopen(img_url, context=ctx, timeout=60) as resp:
            cached.write_bytes(resp.read())
        return cached
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise RuntimeError(
                f"无法下载 UEFI:NTFS 镜像 ({img_url}): {e}\n"
                f"请手动下载 {cache_name} 到 {CACHE_DIR} 或使用 --uefi-ntfs 指定路径"
            ) from e
        # 404：v2.7 已不再提供 .img，改为下载 efi 后构建
    except Exception as e:
        raise RuntimeError(
            f"无法下载 UEFI:NTFS 镜像 ({img_url}): {e}\n"
            f"请手动下载 {cache_name} 到 {CACHE_DIR} 或使用 --uefi-ntfs 指定路径"
        ) from e

    # 2. 下载 bootx64.efi 并构建镜像
    efi_url = f"{UEFI_NTFS_RELEASE_URL}/{efi_name}"
    efi_path = CACHE_DIR / efi_name
    try:
        with urllib.request.urlopen(efi_url, context=ctx, timeout=60) as resp:
            efi_path.write_bytes(resp.read())
    except Exception as e:
        raise RuntimeError(
            f"无法下载 {efi_name} ({efi_url}): {e}\n"
            f"请手动下载 {efi_name} 到 {CACHE_DIR}/ 并重新运行"
        ) from e

    if os.geteuid() != 0:
        raise RuntimeError(
            "构建 UEFI:NTFS 镜像需要 root 权限（losetup/mount）。\n"
            f"请使用 sudo 运行，或手动将 {efi_name} 制作为 {cache_name} 后放到 {CACHE_DIR}"
        )

    _build_img_from_efi(efi_path, cached)
    return cached
