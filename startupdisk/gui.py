"""图形界面"""

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import Tk, filedialog as tk_filedialog, messagebox

import customtkinter as ctk

from .file_dialog import askopenfilename as ctk_askopenfilename

from .device_detector import get_usb_devices, is_device_mounted, unmount_device
from .progress_utils import SpeedEstimator, format_eta_friendly, format_speed
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
    try:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        app = StartupDiskApp()
        app.mainloop()
    except Exception as e:
        msg = str(e) or repr(e)
        print(f"启动失败: {msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        try:
            root = Tk()
            root.withdraw()
            messagebox.showerror("启动失败", msg)
        except Exception:
            pass
        sys.exit(1)


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

        # 刷写进度条 + 百分比
        progress_frame = ctk.CTkFrame(main, fg_color="transparent")
        progress_frame.pack(fill="x", pady=(16, 4))
        self.progress = ctk.CTkProgressBar(progress_frame)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress.set(0)
        self.pct_label = ctk.CTkLabel(
            progress_frame,
            text="0%",
            width=95,
            font=ctk.CTkFont(size=13),
        )
        self.pct_label.pack(side="left", padx=(10, 0))

        # 实时写入速度 + 剩余时间
        speed_frame = ctk.CTkFrame(main, fg_color="transparent")
        speed_frame.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(speed_frame, text="写入速度:", width=70).pack(side="left", padx=(0, 8))
        self.speed_label = ctk.CTkLabel(
            speed_frame,
            text="-- MB/s",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1f538d", "#3b8ed0"),
        )
        self.speed_label.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(speed_frame, text="剩余时间:", width=70).pack(side="left", padx=(0, 8))
        self.eta_label = ctk.CTkLabel(
            speed_frame,
            text="--",
            font=ctk.CTkFont(size=13),
        )
        self.eta_label.pack(side="left", padx=(0, 24))
        self.stop_btn = ctk.CTkButton(
            speed_frame,
            text="强制停止",
            width=80,
            fg_color=("#c75050", "#8b3a3a"),
            hover_color=("#e05050", "#a04040"),
            command=self._stop_create,
        )
        self.stop_btn.pack(side="left")
        self.stop_btn.pack_forget()  # 初始隐藏

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

    def _display_progress(self, bytes_copied: int, total_bytes: int):
        """
        按实际写入 USB 的字节计算进度。
        98% 封顶：防止 total_bytes 评估偏小导致进度超出 100%，
        仅在 writer 报告全部完成后才显示 100%。
        """
        if total_bytes <= 0:
            self.progress.set(0)
            self.pct_label.configure(text="0%")
            return
        pct = bytes_copied / total_bytes
        if bytes_copied >= total_bytes:
            self.progress.set(1.0)
            self.pct_label.configure(text="100%")
        elif pct >= 0.98:
            self.progress.set(0.98)
            self.pct_label.configure(text="98% (收尾中)")
        else:
            self.progress.set(pct)
            self.pct_label.configure(text=f"{int(pct * 100)}%")

    def _start_display_loop(self, speed_estimator: SpeedEstimator, disp: dict):
        """
        等间隔（500ms）刷新进度条、写入速度和剩余时间。

        数据来源：_progress_state（IO 线程写入，主线程读取，GIL 保护）
        速度平滑：两层 EMA
          - SpeedEstimator 内部 EMA（alpha=0.3）：消除 fdatasync 时间波动
          - 展示层 EMA（alpha=0.2）：进一步稳定显示值，避免视觉跳变
        """
        if not self._creating:
            return
        bc = self._progress_state.get("bytes", 0)
        tb = self._progress_state.get("total", 0)
        if tb > 0:
            self._display_progress(bc, tb)
            speed_estimator.update(bc)
            raw_speed = speed_estimator.get_speed_mbs()
            if raw_speed > 0:
                # 展示层 EMA：在 SpeedEstimator EMA 之上再次平滑，
                # 使速度数值缓慢、连续地变化，消除视觉跳变
                if disp["speed_mbs"] <= 0:
                    disp["speed_mbs"] = raw_speed   # 首次初始化
                else:
                    disp["speed_mbs"] = 0.8 * disp["speed_mbs"] + 0.2 * raw_speed
                self.speed_label.configure(text=format_speed(disp["speed_mbs"]))
                remaining_sec = speed_estimator.get_remaining_sec(tb, bc)
                if remaining_sec >= 0:
                    self.eta_label.configure(text=format_eta_friendly(remaining_sec))
        self.after(500, lambda: self._start_display_loop(speed_estimator, disp))

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
                ok, _ = self._run_privileged(["unmount", device])
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
        self._stop_requested = False
        self._create_proc = None
        self._create_cancel_event = None
        self.create_btn.configure(state="disabled")
        self.stop_btn.pack(side="left")
        self.log_text.delete("1.0", "end")
        self.progress.set(0)
        self.pct_label.configure(text="0%")
        self.speed_label.configure(text="-- MB/s")
        self.eta_label.configure(text="--")
        threading.Thread(
            target=self._do_create,
            args=(iso_path, device),
            daemon=True,
        ).start()

    def _get_project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def _get_python_path(self) -> str:
        return sys.executable

    def _stop_create(self):
        """强制停止当前刷写"""
        if not self._creating:
            return
        if not messagebox.askyesno("确认", "确定要强制停止当前的刷写操作吗？\nU 盘可能处于不完整状态。"):
            return
        self._stop_requested = True
        if self._create_proc is not None:
            try:
                pid = self._create_proc.pid
                if pid is not None and pid > 0:
                    try:
                        # 杀进程组：pkexec 及其子进程（实际执行复制的 root 进程）一并退出
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        self._create_proc.kill()
                else:
                    self._create_proc.kill()
            except ProcessLookupError:
                pass
        if self._create_cancel_event is not None:
            self._create_cancel_event.set()

    def _build_create_cmd(self, create_args: list[str]) -> list[str]:
        """构建 create 子进程命令行；root 直接运行，非 root 经 pkexec"""
        python = self._get_python_path()
        # -u 强制无缓冲，确保 [PROGRESS] 行实时输出（参考 python -u、PYTHONUNBUFFERED）
        base = [python, "-u", "-m", "startupdisk"] + create_args
        if _is_root():
            return base
        home = os.environ.get("HOME", "")
        env_parts = ["PYTHONUNBUFFERED=1"]
        if home:
            env_parts.append(f"HOME={home}")
        return ["pkexec", "env"] + env_parts + base

    def _run_create_subprocess(self, create_args: list[str]) -> tuple[bool, str]:
        """
        统一进度数据获取：无论 root 与否，都通过子进程 stdout 的 [PROGRESS] 协议获取进度。
        IO 线程只更新 _progress_state（共享状态），不直接操作 UI；
        UI 刷新由固定 500ms 定时器 _start_display_loop 负责，保证等间隔更新。
        """
        root = self._get_project_root()
        cmd = self._build_create_cmd(create_args)
        lines: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True
            )
            self._create_proc = proc
            for line in proc.stdout:
                s = line.rstrip()
                lines.append(s)
                if s.startswith("[PROGRESS]") and "," in s:
                    try:
                        bc, tb = map(int, s[10:].split(",", 1))
                        if tb > 0:
                            # 只更新共享状态；UI 由定时器统一刷新（GIL 保护，线程安全）
                            self._progress_state["bytes"] = bc
                            self._progress_state["total"] = tb
                    except (ValueError, IndexError):
                        pass
                else:
                    self._log(s)
            proc.wait()
            ok = proc.returncode == 0 and not self._stop_requested
            if not ok and proc.returncode != 0:
                return False, self._extract_error_from_lines(lines)
            return ok, ""
        except FileNotFoundError:
            if not _is_root():
                self._log("未找到 pkexec，请安装 policykit-1")
                return False, "未找到 pkexec，请安装 policykit-1 或 polkit"
            raise
        finally:
            self._create_proc = None

    def _run_privileged(self, args: list[str]) -> tuple[bool, str]:
        """以 root 运行 startupdisk 子命令（如 unmount），不解析进度"""
        root = self._get_project_root()
        python = self._get_python_path()
        if _is_root():
            cmd = [python, "-m", "startupdisk"] + args
        else:
            home = os.environ.get("HOME", "")
            env_parts = ["PYTHONUNBUFFERED=1"]
            if home:
                env_parts.append(f"HOME={home}")
            cmd = ["pkexec", "env"] + env_parts + [python, "-m", "startupdisk"] + args
        try:
            r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=30)
            out = (r.stdout + r.stderr).strip()
            if out:
                self._log(out)
            return r.returncode == 0, "" if r.returncode == 0 else (out or "命令执行失败")
        except FileNotFoundError:
            self._log("未找到 pkexec，请安装 policykit-1")
            return False, "未找到 pkexec"
        except subprocess.TimeoutExpired:
            return False, "执行超时"

    def _extract_error_from_lines(self, lines: list[str]) -> str:
        """从输出行中提取错误信息"""
        for s in reversed(lines):
            if "错误:" in s or "error" in s.lower() or "Error" in s:
                return s.strip() or lines[-1] if lines else "未知错误"
        if lines:
            return lines[-1].strip() or "请查看刷写日志"
        return "子进程异常退出（可能已取消权限验证）"

    def _do_create(self, iso_path: str, device: str):
        try:
            self.progress.set(0)
            self._progress_state = {"bytes": 0, "total": 0}
            speed_estimator = SpeedEstimator(alpha=0.3)
            disp = {"speed_mbs": 0.0}
            self.after(500, lambda: self._start_display_loop(speed_estimator, disp))
            create_args = ["create", "-i", iso_path, "-d", device, "-y"]
            ok, err_msg = self._run_create_subprocess(create_args)
            if self._stop_requested:
                self.after(0, lambda: messagebox.showwarning("已停止", "刷写已强制停止。\nU 盘可能处于不完整状态，请重新制作或格式化。"))
            elif not ok:
                raise RuntimeError(err_msg or "制作失败，请查看刷写日志")
            else:
                self.after(0, lambda: messagebox.showinfo("完成", "启动盘制作成功！\n请安全弹出 U 盘。"))
        except Exception as e:
            if self._stop_requested:
                self.after(0, lambda: messagebox.showwarning("已停止", "刷写已强制停止。"))
            else:
                msg = str(e) or repr(e)
                self._log(f"错误: {msg}")
                self.after(0, lambda: messagebox.showerror("错误", msg))
        finally:
            self.after(0, self._on_create_done)

    def _on_create_done(self):
        self._creating = False
        self._create_proc = None
        self._create_cancel_event = None
        self.create_btn.configure(state="normal")
        self.stop_btn.pack_forget()
        if not self._stop_requested:
            self.progress.set(1)
            self.pct_label.configure(text="100%")
        self.speed_label.configure(text="-- MB/s")
        self.eta_label.configure(text="--")
