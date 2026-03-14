"""图形界面"""

import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .creator import create_startup_disk
from .device_detector import get_usb_devices, is_device_mounted
from .installer import (
    check_python_deps,
    check_system_deps,
    get_system_install_command,
    run_pipenv_install,
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

        # 标题
        title = ctk.CTkLabel(
            main,
            text="Windows 10/11 启动盘制作",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.pack(anchor="w", pady=(0, 16))

        if not _is_root():
            warn = ctk.CTkLabel(
                main,
                text="⚠ 需要 root 权限，请使用: sudo pipenv run python -m startupdisk gui",
                font=ctk.CTkFont(size=13),
                text_color="#ff9800",
            )
            warn.pack(anchor="w", pady=(0, 12))

        # 一键安装区域
        self._build_install_section(main)

        # ISO 选择
        iso_frame = ctk.CTkFrame(main, fg_color="transparent")
        iso_frame.pack(fill="x", pady=8)
        ctk.CTkLabel(iso_frame, text="ISO 文件:", width=80).pack(side="left", padx=(0, 8))
        self.iso_entry = ctk.CTkEntry(iso_frame, placeholder_text="选择 Windows ISO 文件...")
        self.iso_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(iso_frame, text="浏览", width=80, command=self._browse_iso).pack(
            side="left", padx=(8, 0)
        )

        # USB 设备选择
        usb_frame = ctk.CTkFrame(main, fg_color="transparent")
        usb_frame.pack(fill="x", pady=8)
        ctk.CTkLabel(usb_frame, text="目标 U 盘:", width=80).pack(side="left", padx=(0, 8))
        self.usb_var = ctk.StringVar()
        self.usb_combo = ctk.CTkComboBox(
            usb_frame,
            values=["点击刷新"],
            variable=self.usb_var,
            state="readonly",
            width=280,
        )
        self.usb_combo.pack(side="left")
        ctk.CTkButton(usb_frame, text="刷新", width=80, command=self._refresh_devices).pack(
            side="left", padx=(8, 0)
        )

        # 创建按钮
        self.create_btn = ctk.CTkButton(
            main,
            text="开始制作",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            command=self._start_create,
        )
        self.create_btn.pack(fill="x", pady=16)

        # 进度条
        self.progress = ctk.CTkProgressBar(main)
        self.progress.pack(fill="x", pady=(0, 8))
        self.progress.set(0)

        # 日志区域
        ctk.CTkLabel(main, text="日志:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.log_text = ctk.CTkTextbox(main, height=180, font=ctk.CTkFont(family="Monospace"))
        self.log_text.pack(fill="both", expand=True, pady=(4, 0))

        self.after(100, self._refresh_devices)
        self.after(200, self._update_install_status)

    def _build_install_section(self, parent):
        """依赖安装区域"""
        install_frame = ctk.CTkFrame(parent, fg_color=("gray85", "gray25"))
        install_frame.pack(fill="x", pady=(0, 12))

        inner = ctk.CTkFrame(install_frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            inner,
            text="依赖安装",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")

        status_frame = ctk.CTkFrame(inner, fg_color="transparent")
        status_frame.pack(fill="x", pady=(6, 4))
        self.py_status = ctk.CTkLabel(status_frame, text="Python: 检测中...", font=ctk.CTkFont(size=12))
        self.py_status.pack(anchor="w")
        self.sys_status = ctk.CTkLabel(status_frame, text="系统: 检测中...", font=ctk.CTkFont(size=12))
        self.sys_status.pack(anchor="w")

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(4, 0))
        self.install_py_btn = ctk.CTkButton(
            btn_frame, text="一键安装 Python 依赖 (pipenv install)", width=220, command=self._do_install_python
        )
        self.install_py_btn.pack(side="left", padx=(0, 8))
        self.install_sys_btn = ctk.CTkButton(
            btn_frame, text="一键安装系统依赖", width=140, command=self._do_install_system
        )
        self.install_sys_btn.pack(side="left")

    def _update_install_status(self):
        """更新依赖状态显示"""
        py_ok, py_missing = check_python_deps()
        sys_ok, sys_missing = check_system_deps()
        self.py_status.configure(
            text=f"Python: ✓ 就绪" if py_ok else f"Python: 缺少 {', '.join(py_missing)}",
            text_color=("#2e7d32" if py_ok else "#d32f2f"),
        )
        self.sys_status.configure(
            text=f"系统: ✓ 就绪" if sys_ok else f"系统: 缺少 {', '.join(sys_missing)}",
            text_color=("#2e7d32" if sys_ok else "#d32f2f"),
        )

    def _do_install_python(self):
        """执行 pipenv install"""
        self.install_py_btn.configure(state="disabled")
        self.log_text.insert("end", "正在安装 Python 依赖 (pipenv install)...\n")

        def _run():
            def log(msg):
                self.after(0, lambda: self._log(msg))

            ok, out = run_pipenv_install(log_callback=log)
            self.after(0, lambda: self._on_install_done(ok, out, self.install_py_btn, "Python"))

        threading.Thread(target=_run, daemon=True).start()

    def _do_install_system(self):
        """执行系统依赖安装"""
        if not messagebox.askyesno("确认", "将弹出权限窗口安装系统依赖 (parted, ntfs-3g, python3-tk)。\n继续？"):
            return
        self.install_sys_btn.configure(state="disabled")
        desc, args = get_system_install_command()
        self.log_text.insert("end", f"正在安装系统依赖 ({desc})...\n")
        self.log_text.insert("end", f"命令: sudo {' '.join(args)}\n")

        def _run():
            def log(msg):
                self.after(0, lambda: self._log(msg))

            ok, out = run_system_install(log_callback=log)
            self.after(0, lambda: self._on_install_done(ok, out, self.install_sys_btn, "系统"))

        threading.Thread(target=_run, daemon=True).start()

    def _on_install_done(self, ok: bool, out: str, btn, kind: str):
        btn.configure(state="normal")
        self._update_install_status()
        if ok:
            messagebox.showinfo(f"{kind}依赖安装", "安装成功！")
        else:
            messagebox.showwarning(f"{kind}依赖安装", f"安装未完成:\n\n{out[:500]}")

    def _log(self, msg: str):
        def _append():
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")

        self.after(0, _append)

    def _browse_iso(self):
        path = filedialog.askopenfilename(
            title="选择 Windows ISO",
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
        if not sel or sel.startswith("未检测") or sel.startswith("刷新"):
            messagebox.showerror("错误", "请选择目标 U 盘")
            return
        device = sel.split()[0]
        if not device.startswith("/dev/"):
            messagebox.showerror("错误", "无效的设备")
            return
        if is_device_mounted(device):
            messagebox.showerror("错误", f"{device} 已挂载，请先卸载")
            return
        if not messagebox.askyesno(
            "确认",
            f"即将格式化 {device} 并写入 {Path(iso_path).name}\n\n此操作将清除 U 盘上的所有数据！\n\n确认继续？",
        ):
            return

        self._creating = True
        self.create_btn.configure(state="disabled")
        self.log_text.delete("1.0", "end")
        self.progress.set(0)
        threading.Thread(
            target=self._do_create,
            args=(iso_path, device),
            daemon=True,
        ).start()

    def _do_create(self, iso_path: str, device: str):
        try:
            def log(msg: str):
                self._log(msg)

            def progress(cur: int, total: int, name: str):
                def _update():
                    if total > 0:
                        self.progress.set(cur / total)
                    else:
                        self.progress.set(0)

                self.after(0, _update)

            create_startup_disk(
                iso_path,
                device,
                log_callback=log,
                progress_callback=progress,
            )
            self.after(0, lambda: messagebox.showinfo("完成", "启动盘制作成功！\n请安全弹出 U 盘。"))
        except Exception as e:
            self._log(f"错误: {e}")
            self.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.after(0, self._on_create_done)

    def _on_create_done(self):
        self._creating = False
        self.create_btn.configure(state="normal")
        self.progress.set(1)
