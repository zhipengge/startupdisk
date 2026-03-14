"""图形界面"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog as tk_filedialog
from tkinter import messagebox

import customtkinter as ctk

from .file_dialog import askopenfilename as ctk_askopenfilename

from .device_detector import get_usb_devices, is_device_mounted, unmount_device
from .installer import (
    check_python_deps,
    check_system_deps,
    get_system_install_command,
    run_python_deps_install,
    run_system_install,
)


def _is_root() -> bool:
    return os.geteuid() == 0


def run_gui():
    """启动 GUI 主窗口"""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = StartupDiskApp()
    app.mainloop()


class StartupDiskApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Windows 启动盘制作工具")
        self.geometry("620x520")
        self.minsize(500, 450)

        self._creating = False
        self._build_ui()

    def _build_ui(self):
        # 主容器
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        # 头部：logo + 标题
        header_frame = ctk.CTkFrame(main, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 16))
        logo_path = Path(__file__).resolve().parent.parent / "logo.png"
        if logo_path.exists():
            try:
                from PIL import Image
                pil_img = Image.open(logo_path).convert("RGBA")
                logo_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(48, 48))
                logo_label = ctk.CTkLabel(header_frame, image=logo_img, text="")
                logo_label.pack(side="left", padx=(0, 12))
            except Exception:
                pass
        title = ctk.CTkLabel(
            header_frame,
            text="Windows 10/11 启动盘制作",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.pack(side="left", anchor="w")

        if not _is_root():
            warn = ctk.CTkLabel(
                main,
                text="制作时将弹出权限窗口",
                font=ctk.CTkFont(size=13),
                text_color="#ff9800",
            )
            warn.pack(anchor="w", pady=(0, 12))

        # 行1：ISO 文件选择（标签 | 输入框 | 浏览）
        iso_frame = ctk.CTkFrame(main, fg_color="transparent")
        iso_frame.pack(fill="x", pady=8)
        ctk.CTkLabel(iso_frame, text="ISO 文件:", width=80).pack(side="left", padx=(0, 8))
        self.iso_entry = ctk.CTkEntry(iso_frame, placeholder_text="选择 Windows ISO 文件...")
        self.iso_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(iso_frame, text="浏览", width=90, command=self._browse_iso).pack(side="left")

        # 行2：目标 U 盘（标签 | 下拉框 | 开始制作）
        usb_frame = ctk.CTkFrame(main, fg_color="transparent")
        usb_frame.pack(fill="x", pady=8)
        ctk.CTkLabel(usb_frame, text="目标 U 盘:", width=80).pack(side="left", padx=(0, 8))
        self.usb_var = ctk.StringVar()
        self.usb_combo = ctk.CTkComboBox(
            usb_frame,
            values=["加载中..."],
            variable=self.usb_var,
            state="readonly",
        )
        self.usb_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.create_btn = ctk.CTkButton(
            usb_frame,
            text="开始制作",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=90,
            command=self._start_create,
        )
        self.create_btn.pack(side="left")

        # 刷写进度条
        progress_frame = ctk.CTkFrame(main, fg_color="transparent")
        progress_frame.pack(fill="x", pady=(16, 4))
        self.progress = ctk.CTkProgressBar(progress_frame)
        self.progress.pack(fill="x")
        self.progress.set(0)

        # 实时写入速度（单独区域）
        speed_frame = ctk.CTkFrame(main, fg_color="transparent")
        speed_frame.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(speed_frame, text="写入速度:", width=70).pack(side="left", padx=(0, 8))
        self.speed_label = ctk.CTkLabel(
            speed_frame,
            text="-- MB/s",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1f538d", "#3b8ed0"),
        )
        self.speed_label.pack(side="left")

        # 刷写日志（仅显示刷写内容，不含进度）
        ctk.CTkLabel(main, text="刷写日志:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.log_text = ctk.CTkTextbox(main, height=180, font=ctk.CTkFont(family="Monospace"))
        self.log_text.pack(fill="both", expand=True, pady=(4, 0))

        self.after(100, self._refresh_devices)
        self.after(500, self._auto_check_and_install_deps)

    def _auto_check_and_install_deps(self):
        """启动时自动检查并安装缺失依赖"""
        def _run():
            py_ok, py_missing = check_python_deps()
            sys_ok, sys_missing = check_system_deps()
            if not py_ok:
                self.after(0, lambda: self._log("正在安装 Python 依赖..."))
                ok, _ = run_python_deps_install(log_callback=lambda m: self.after(0, lambda x=m: self._log(x)))
                self.after(0, lambda: self._log("Python 依赖安装完成" if ok else "Python 依赖安装失败"))
            if not sys_ok:
                self.after(0, lambda: self._log("检测到缺少系统依赖，正在安装（将弹出权限窗口）..."))
                ok, out = run_system_install(log_callback=lambda m: self.after(0, lambda x=m: self._log(x)))
                msg = "系统依赖安装完成" if ok else "系统依赖安装未完成，请手动执行: sudo apt install parted ntfs-3g python3-tk"
                self.after(0, lambda m=msg: self._log(m))

        threading.Thread(target=_run, daemon=True).start()

    def _log(self, msg: str):
        def _append():
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")

        self.after(0, _append)

    def _update_progress_from_subprocess(self, bytes_copied: int, total_bytes: int, last: dict):
        """根据子进程的 [PROGRESS] 输出更新进度条和写入速度"""
        if total_bytes > 0:
            self.progress.set(bytes_copied / total_bytes)
        now = time.monotonic()
        if last["bytes"] is not None and last["time"] is not None:
            dt = now - last["time"]
            if dt >= 0.2:
                speed_mbs = (bytes_copied - last["bytes"]) / dt / (1024 * 1024)
                self.speed_label.configure(text=f"{speed_mbs:.1f} MB/s")
        last["bytes"] = bytes_copied
        last["time"] = now

    def _browse_iso(self):
        initial = Path.home() / "Downloads"
        if not initial.is_dir():
            initial = Path.home()
        try:
            path = tk_filedialog.askopenfilename(
                parent=self,
                title="选择 Windows ISO",
                initialdir=str(initial),
                filetypes=[("ISO 镜像", "*.iso"), ("全部文件", "*.*")],
            )
        except Exception:
            path = ctk_askopenfilename(
                parent=self,
                title="选择 Windows ISO",
                initialdir=initial,
                filetypes=[("ISO 镜像", "*.iso"), ("全部文件", "*.*")],
            )
        if path:
            self.iso_entry.delete(0, "end")
            self.iso_entry.insert(0, path)

    def _refresh_devices(self):
        try:
            devices = get_usb_devices()
            if not devices:
                values = ["未检测到 USB 设备"]
                self._log("已刷新: 未检测到可用 U 盘（需可移除、≥4GB）")
            else:
                values = [f"{d.device}  {d.size}  {d.model}" for d in devices]
                self._log(f"已刷新: 发现 {len(devices)} 个 U 盘")
            self.usb_combo.configure(values=values)
            self.usb_var.set(values[0] if values else "")
        except Exception as e:
            self._log(f"刷新失败: {e}")
            self.usb_combo.configure(values=["刷新失败"])

    def _start_create(self):
        if self._creating:
            return
        iso_path = self.iso_entry.get().strip()
        if not iso_path:
            messagebox.showerror("错误", "请选择 ISO 文件")
            return
        if not Path(iso_path).exists():
            messagebox.showerror("错误", f"ISO 文件不存在: {iso_path}")
            return
        sel = self.usb_var.get()
        if not sel or sel.startswith("未检测") or sel.startswith("加载中") or sel.startswith("刷新"):
            messagebox.showerror("错误", "请选择目标 U 盘")
            return
        device = sel.split()[0]
        if not device.startswith("/dev/"):
            messagebox.showerror("错误", "无效的设备")
            return
        if is_device_mounted(device):
            if not _is_root():
                ok = self._run_privileged(["unmount", device])
                if not ok:
                    messagebox.showerror("错误", "卸载失败，请尝试手动卸载")
                    return
            else:
                ok, msg = unmount_device(device)
                if not ok:
                    messagebox.showerror("错误", f"{device} 已挂载，自动卸载失败:\n{msg}")
                    return
            self._log(f"已卸载 {device}")
        if not messagebox.askyesno(
            "确认",
            f"即将格式化 {device} 并写入 {Path(iso_path).name}\n\n此操作将清除 U 盘上的所有数据！\n\n确认继续？",
        ):
            return

        self._creating = True
        self.create_btn.configure(state="disabled")
        self.log_text.delete("1.0", "end")
        self.progress.set(0)
        self.speed_label.configure(text="-- MB/s")
        threading.Thread(
            target=self._do_create,
            args=(iso_path, device),
            daemon=True,
        ).start()

    def _get_project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def _get_python_path(self) -> str:
        return sys.executable

    def _run_privileged(self, args: list[str]) -> bool:
        """以 root 运行 startupdisk 子命令，返回是否成功"""
        root = self._get_project_root()
        cmd = ["pkexec", self._get_python_path(), "-m", "startupdisk"] + args
        _speed_last = {"bytes": None, "time": None}
        try:
            proc = subprocess.Popen(
                cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                s = line.rstrip()
                if s.startswith("[PROGRESS]") and "," in s:
                    try:
                        bc, tb = map(int, s[10:].split(",", 1))
                        if tb > 0:
                            self.after(0, lambda b=bc, t=tb: self._update_progress_from_subprocess(b, t, _speed_last))
                    except (ValueError, IndexError):
                        pass
                else:
                    self._log(s)
            proc.wait()
            return proc.returncode == 0
        except FileNotFoundError:
            self._log("未找到 pkexec，请安装 policykit-1")
            return False
        except subprocess.TimeoutExpired:
            self._log("执行超时")
            return False

    def _do_create(self, iso_path: str, device: str):
        try:
            if _is_root():
                def log(msg: str):
                    self._log(msg)
                _last = {"bytes": None, "time": None}
                def progress(cur: int, total: int, name: str, bytes_copied: int = 0, total_bytes: int = 0):
                    def _update():
                        # 进度条展示进度
                        if total_bytes > 0 and bytes_copied >= 0:
                            self.progress.set(bytes_copied / total_bytes)
                        elif total > 0:
                            self.progress.set(cur / total)
                        else:
                            self.progress.set(0)
                        # 速度标签
                        if total_bytes > 0 and bytes_copied >= 0:
                            now = time.monotonic()
                            if _last["bytes"] is not None and _last["time"] is not None:
                                dt = now - _last["time"]
                                if dt >= 0.3:
                                    speed_mbs = (bytes_copied - _last["bytes"]) / dt / (1024 * 1024)
                                    self.speed_label.configure(text=f"{speed_mbs:.1f} MB/s")
                            _last["bytes"] = bytes_copied
                            _last["time"] = now
                    self.after(0, _update)
                from .creator import create_startup_disk
                create_startup_disk(iso_path, device, log_callback=log, progress_callback=progress)
            else:
                self.progress.set(0)
                ok = self._run_privileged(["create", "-i", iso_path, "-d", device, "-y"])
                if not ok:
                    raise RuntimeError("制作失败")
            self.after(0, lambda: messagebox.showinfo("完成", "启动盘制作成功！\n请安全弹出 U 盘。"))
        except Exception as e:
            msg = str(e) or repr(e)
            self._log(f"错误: {msg}")
            self.after(0, lambda: messagebox.showerror("错误", msg))
        finally:
            self.after(0, self._on_create_done)

    def _on_create_done(self):
        self._creating = False
        self.create_btn.configure(state="normal")
        self.progress.set(1)
        self.speed_label.configure(text="-- MB/s")
