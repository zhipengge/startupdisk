"""依赖检测与一键安装"""

import os
import platform
import shutil
import subprocess
from pathlib import Path


def _detect_distro() -> str:
    """检测 Linux 发行版"""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return ""


def get_system_install_command() -> tuple[str, list[str]]:
    """
    返回 (描述, 安装命令列表)
    如 ("Ubuntu/Debian", ["sudo", "apt", "install", "-y", "parted", "ntfs-3g", "python3-tk"])
    """
    distro = _detect_distro()
    packages = ["parted", "ntfs-3g", "python3-tk"]
    if distro in ("ubuntu", "debian", "linuxmint", "pop"):
        return "Ubuntu/Debian", ["apt", "install", "-y"] + packages
    if distro in ("fedora", "rhel", "centos"):
        return "Fedora/RHEL", ["dnf", "install", "-y", "parted", "ntfs-3g", "python3-tkinter"]
    if distro == "arch":
        return "Arch", ["pacman", "-S", "--noconfirm", "parted", "ntfs-3g", "tk"]
    return "当前发行版", ["echo", "请手动安装: parted ntfs-3g python3-tk"]


def check_system_deps() -> tuple[bool, list[str]]:
    """检查系统依赖，返回 (是否齐全, 缺失列表)"""
    missing = []
    if not shutil.which("parted"):
        missing.append("parted")
    if not shutil.which("mkfs.ntfs"):
        missing.append("ntfs-3g")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        missing.append("python3-tk")
    return len(missing) == 0, missing


def check_python_deps() -> tuple[bool, list[str]]:
    """检查 Python 依赖，返回 (是否齐全, 缺失列表)"""
    missing = []
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        missing.append("customtkinter")
    return len(missing) == 0, missing


def get_project_root() -> Path:
    """获取项目根目录（含 Pipfile 的目录）"""
    # 从当前文件向上查找 Pipfile
    p = Path(__file__).resolve().parent
    for _ in range(5):
        if (p / "Pipfile").exists():
            return p
        p = p.parent
    return Path.cwd()


def run_pipenv_install(log_callback=None) -> tuple[bool, str]:
    """
    执行 pipenv install
    返回 (成功, 输出信息)
    """
    root = get_project_root()
    try:
        result = subprocess.run(
            ["pipenv", "install"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (result.stdout + result.stderr).strip() if result.returncode != 0 else result.stdout.strip()
        if log_callback:
            log_callback(out)
        return result.returncode == 0, out or ("安装成功" if result.returncode == 0 else "安装失败")
    except FileNotFoundError:
        msg = "未找到 pipenv，请先安装: pip install pipenv"
        if log_callback:
            log_callback(msg)
        return False, msg
    except subprocess.TimeoutExpired:
        msg = "安装超时"
        if log_callback:
            log_callback(msg)
        return False, msg
    except Exception as e:
        msg = str(e)
        if log_callback:
            log_callback(msg)
        return False, msg


def run_system_install(log_callback=None) -> tuple[bool, str]:
    """
    尝试通过 pkexec 执行系统包安装
    返回 (成功, 输出信息)
    """
    if platform.system() != "Linux":
        return False, "仅支持 Linux"
    desc, args = get_system_install_command()
    # 使用 pkexec 提权（会弹出密码框）；args[0] 为 apt/dnf/pacman
    cmd = ["pkexec", args[0]] + args[1:]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (result.stdout + result.stderr).strip()
        if log_callback:
            log_callback(f"执行: {' '.join(cmd)}\n{out}")
        return result.returncode == 0, out or ("安装成功" if result.returncode == 0 else "安装失败")
    except FileNotFoundError:
        # 无 pkexec 时返回手动命令
        manual_cmd = f"sudo {' '.join(args)}"
        msg = f"请手动在终端执行:\n{manual_cmd}"
        if log_callback:
            log_callback(msg)
        return False, msg
    except subprocess.TimeoutExpired:
        msg = "安装超时"
        if log_callback:
            log_callback(msg)
        return False, msg
    except Exception as e:
        msg = str(e)
        if log_callback:
            log_callback(msg)
        return False, msg
