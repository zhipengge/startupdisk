#!/usr/bin/env python3
"""Linux 下 Windows 启动盘制作工具 - 命令行入口"""

import argparse
import sys
from pathlib import Path

from .creator import create_startup_disk
from .device_detector import get_usb_devices, is_device_mounted, unmount_device


def main():
    parser = argparse.ArgumentParser(
        description="在 Linux 下制作 Windows 10/11 UEFI 启动盘",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出可用 U 盘
  %(prog)s list

  # 制作启动盘（需 root）
  sudo %(prog)s create -i /path/to/Win11.iso -d /dev/sdb

依赖: parted, ntfs-3g, wipefs, mount
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出可用的 USB 设备")
    list_parser.set_defaults(func=cmd_list)
    
    # gui 命令
    gui_parser = subparsers.add_parser("gui", help="启动图形界面")
    gui_parser.set_defaults(func=cmd_gui)

    # create 命令
    create_parser = subparsers.add_parser("create", help="制作 Windows 启动盘")
    create_parser.add_argument("-i", "--iso", required=True, help="Windows ISO 文件路径")
    create_parser.add_argument("-d", "--device", required=True, help="目标 USB 设备，如 /dev/sdb")
    create_parser.add_argument(
        "--uefi-ntfs",
        help="UEFI:NTFS 镜像路径（不指定则自动下载）",
    )
    create_parser.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    create_parser.set_defaults(func=cmd_create)

    unmount_parser = subparsers.add_parser("unmount", help="卸载 USB 设备")
    unmount_parser.add_argument("device", help="设备路径，如 /dev/sdb")
    unmount_parser.set_defaults(func=cmd_unmount)
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


def cmd_gui(args):
    """启动图形界面"""
    try:
        from .gui import run_gui
        run_gui()
    except ImportError:
        project_dir = Path(__file__).resolve().parent.parent
        print("错误: GUI 依赖未安装。请执行: pipenv install", file=sys.stderr)
        print(f"  或: cd {project_dir} && .venv/bin/pip install customtkinter Pillow", file=sys.stderr)
        sys.exit(1)


def cmd_list(args):
    """列出 USB 设备"""
    devices = get_usb_devices()
    if not devices:
        print("未检测到可用的 USB 设备（需可移除、容量≥4GB）")
        sys.exit(1)
    print("可用的 USB 设备：")
    for i, d in enumerate(devices, 1):
        print(f"  {i}. {d.device}  {d.size:>10}  {d.model}")
    print("\n使用示例: sudo startupdisk create -i WIN11.ISO -d /dev/sdb")


def cmd_create(args):
    """制作启动盘"""
    iso_path = Path(args.iso)
    if not iso_path.exists():
        print(f"错误: ISO 文件不存在: {iso_path}")
        sys.exit(1)
    
    device = args.device
    if not device.startswith("/dev/"):
        device = f"/dev/{device}"
    
    # 检查设备
    devices = get_usb_devices()
    device_paths = [d.device for d in devices]
    if device not in device_paths:
        print(f"错误: {device} 不是可用的 USB 设备")
        print("可用设备:", ", ".join(device_paths) or "无")
        sys.exit(1)
    
    if is_device_mounted(device):
        ok, msg = unmount_device(device)
        if not ok:
            print(f"错误: {device} 已挂载，自动卸载失败: {msg}")
            sys.exit(1)
        print(f"已卸载: {device}")
    
    if not args.yes:
        print(f"\n即将格式化 {device} 并写入 {iso_path.name}")
        print("此操作将清除 U 盘上的所有数据！")
        confirm = input("确认继续？(yes/no): ")
        if confirm.lower() != "yes":
            print("已取消")
            sys.exit(0)
    
    try:
        def progress(cur, total, name, *args):
            if len(args) >= 2 and args[1] > 0:
                bc, tb = int(args[0]), int(args[1])
                if sys.stdout.isatty():
                    pct = bc * 100 // tb
                    print(f"\r  进度: {pct}% ", end="", flush=True)
                else:
                    print(f"[PROGRESS]{bc},{tb}", flush=True)
            elif total > 0 and sys.stdout.isatty():
                pct = cur * 100 // total
                print(f"\r  进度: {pct}% ({cur}/{total})", end="", flush=True)

        create_startup_disk(
            iso_path,
            device,
            uefi_ntfs_path=args.uefi_ntfs,
            log_callback=lambda m: print(m),
            progress_callback=progress,
        )
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_unmount(args):
    """卸载设备"""
    device = args.device if args.device.startswith("/dev/") else f"/dev/{args.device}"
    ok, msg = unmount_device(device)
    if ok:
        print(msg)
    else:
        print(f"错误: {msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
