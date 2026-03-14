"""UEFI:NTFS 引导镜像下载与管理"""

import platform
import ssl
import urllib.request
from pathlib import Path


UEFI_NTFS_RELEASE_URL = "https://github.com/pbatard/uefi-ntfs/releases/download/v2.7"
CACHE_DIR = Path.home() / ".cache" / "startupdisk"


def _get_arch_filename() -> str:
    """根据系统架构返回对应的 uefi-ntfs 镜像文件名"""
    machine = platform.machine().lower()
    arch_map = {
        "x86_64": "uefi-ntfs_x64.img",
        "amd64": "uefi-ntfs_x64.img",
        "aarch64": "uefi-ntfs_arm64.img",
        "armv8l": "uefi-ntfs_arm64.img",
        "arm64": "uefi-ntfs_arm64.img",
    }
    return arch_map.get(machine, "uefi-ntfs_x64.img")


def get_uefi_ntfs_path(custom_path: str | None = None) -> Path:
    """
    获取 uefi-ntfs.img 路径
    优先使用用户指定路径，否则从缓存或下载
    """
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"指定的 UEFI:NTFS 镜像不存在: {custom_path}")
    
    filename = _get_arch_filename()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / filename
    
    if cached.exists():
        return cached
    
    # 下载
    url = f"{UEFI_NTFS_RELEASE_URL}/{filename}"
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=60) as resp:
            data = resp.read()
        cached.write_bytes(data)
        return cached
    except Exception as e:
        raise RuntimeError(
            f"无法下载 UEFI:NTFS 镜像 ({url}): {e}\n"
            f"请手动下载 {filename} 到 {CACHE_DIR} 或使用 --uefi-ntfs 指定路径"
        ) from e
