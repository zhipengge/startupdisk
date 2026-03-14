"""USB 设备检测模块"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class USBDevice:
    """USB 设备信息"""
    device: str          # 如 /dev/sdb
    model: str           # 设备型号
    size: str            # 容量
    size_bytes: int      # 字节数
    removable: bool      # 是否可移除
    path: Path           # /sys 路径


def _get_lsblk_json() -> dict:
    """获取 lsblk JSON 输出"""
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,SIZE,MODEL,RM", "-b", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        raise RuntimeError(f"无法执行 lsblk: {e}") from e


def _parse_size(size_str: str) -> int:
    """解析 lsblk 的 SIZE 字段（字节）"""
    try:
        return int(size_str)
    except (ValueError, TypeError):
        return 0


def get_usb_devices() -> list[USBDevice]:
    """
    获取可用的 USB 设备列表
    通过 lsblk 和 /sys/block 信息识别可移除块设备
    """
    devices: list[USBDevice] = []
    data = _get_lsblk_json()
    
    for block in data.get("blockdevices", []):
        name = block.get("name")
        if not name:
            continue
        # 跳过 virtio、loop、nvme 等
        if name.startswith(("loop", "sr", "dm-", "vd", "xvd", "nvme")):
            continue
        # 只处理可移除设备（RM=true 多为 U 盘）
        if not block.get("rm", False):
            continue
        size_bytes = _parse_size(str(block.get("size", 0)))
        # 最小 4GB
        if size_bytes < 4 * 1024**3:
            continue
        # 格式化容量显示
        if size_bytes >= 1024**3:
            size_str = f"{size_bytes / 1024**3:.1f}G"
        elif size_bytes >= 1024**2:
            size_str = f"{size_bytes / 1024**2:.0f}M"
        else:
            size_str = str(size_bytes)
        devices.append(USBDevice(
            device=f"/dev/{name}",
            model=(block.get("model") or "").strip() or "(未知型号)",
            size=size_str,
            size_bytes=size_bytes,
            removable=block.get("rm", False),
            path=Path("/sys/block") / name,
        ))
    
    return devices


def get_partitions(device: str) -> list[str]:
    """获取设备的分区列表"""
    device_name = Path(device).name
    block_path = Path("/sys/block") / device_name
    if not block_path.exists():
        return []
    partitions = []
    for entry in block_path.iterdir():
        if entry.name.startswith(device_name) and entry.name != device_name:
            partitions.append(f"/dev/{entry.name}")
    return sorted(partitions)


def _get_mounted_targets(device: str) -> list[str]:
    """获取设备及其分区已挂载的挂载点列表"""
    targets = []
    try:
        # 检查设备本身
        result = subprocess.run(
            ["findmnt", "-S", device, "-n", "-o", "TARGET"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            targets.extend(result.stdout.strip().split("\n"))
        # 检查分区
        for part in get_partitions(device):
            r = subprocess.run(
                ["findmnt", "-S", part, "-n", "-o", "TARGET"],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0 and r.stdout.strip():
                targets.extend(r.stdout.strip().split("\n"))
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return targets


def is_device_mounted(device: str) -> bool:
    """检查设备或其分区是否已挂载"""
    return len(_get_mounted_targets(device)) > 0


def unmount_device(device: str) -> tuple[bool, str]:
    """
    卸载设备及其所有分区的挂载点
    返回 (成功, 消息)
    """
    targets = _get_mounted_targets(device)
    if not targets:
        return True, "设备未挂载"
    # 先卸载深层挂载点
    targets.sort(key=len, reverse=True)
    errors = []
    for target in targets:
        try:
            r = subprocess.run(
                ["umount", target],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode != 0:
                errors.append(f"{target}: {r.stderr.strip() or r.stdout.strip() or '卸载失败'}")
        except subprocess.TimeoutExpired:
            errors.append(f"{target}: 超时")
        except Exception as e:
            errors.append(f"{target}: {e}")
    if errors:
        return False, "\n".join(errors)
    return True, f"已卸载 {len(targets)} 个挂载点"
