"""自定义文件选择对话框，风格与主应用一致"""

from pathlib import Path

import customtkinter as ctk


def askopenfilename(
    parent=None,
    title="选择文件",
    initialdir: str | Path | None = None,
    filetypes: list[tuple[str, str]] | None = None,
) -> str | None:
    """
    弹出文件选择对话框
    filetypes: [(描述, 模式), ...] 如 [("ISO 镜像", "*.iso"), ("全部", "*.*")]
    返回选中文件路径，取消返回 None
    """
    initialdir = initialdir or Path.home()
    initialdir = Path(initialdir).resolve()
    if not initialdir.is_dir():
        initialdir = Path.home()

    filetypes = filetypes or [("全部文件", "*.*")]
    result: list[str | None] = [None]

    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    dlg.geometry("520x380")
    dlg.minsize(400, 320)

    if parent:
        dlg.transient(parent)
        try:
            dlg.geometry(f"520x380+{parent.winfo_x() + 50}+{parent.winfo_y() + 50}")
        except Exception:
            pass

    main = ctk.CTkFrame(dlg, fg_color="transparent")
    main.pack(fill="both", expand=True, padx=16, pady=16)

    # 当前路径
    path_var = ctk.StringVar(value=str(initialdir))
    path_frame = ctk.CTkFrame(main, fg_color="transparent")
    path_frame.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(path_frame, text="路径:", width=40).pack(side="left", padx=(0, 8))
    path_entry = ctk.CTkEntry(path_frame, textvariable=path_var, height=32)
    path_entry.pack(side="left", fill="x", expand=True)

    def go_path():
        p = Path(path_var.get())
        if p.is_dir():
            refresh_list(p)

    ctk.CTkButton(path_frame, text="转到", width=60, height=32, command=go_path).pack(
        side="left", padx=(8, 0)
    )
    items: list[tuple[str, Path, bool]] = []
    iso_only_var = ctk.BooleanVar(value=True)

    def toggle_iso_only():
        p = Path(path_var.get())
        if p.is_dir():
            refresh_list(p)

    ctk.CTkCheckBox(path_frame, text="仅 ISO", variable=iso_only_var, width=80, command=toggle_iso_only).pack(
        side="left", padx=(12, 0)
    )

    # 文件列表
    list_frame = ctk.CTkFrame(main, fg_color=("gray90", "gray20"))
    list_frame.pack(fill="both", expand=True, pady=(0, 12))
    listbox = ctk.CTkTextbox(list_frame, font=ctk.CTkFont(family="Monospace", size=13), wrap="none")
    listbox.pack(fill="both", expand=True, padx=2, pady=2)

    def refresh_list(cur: Path):
        path_var.set(str(cur))
        listbox.delete("1.0", "end")
        items.clear()
        show_iso_only = iso_only_var.get()
        try:
            dirs = sorted([p for p in cur.iterdir() if p.is_dir() and not p.name.startswith(".")])
            isos = sorted([p for p in cur.iterdir() if p.is_file() and p.suffix.lower() == ".iso"])
            others = [] if show_iso_only else sorted([p for p in cur.iterdir() if p.is_file() and p not in isos])
            for p in dirs:
                items.append((f"📁 {p.name}/", p, True))
            for p in isos:
                size_mb = p.stat().st_size / (1024 * 1024)
                items.append((f"   {p.name}  ({size_mb:.1f} MB)", p, False))
            for p in others[:50]:
                items.append((f"   {p.name}", p, False))
            if len(others) > 50:
                items.append((f"   ... 还有 {len(others) - 50} 个文件", cur, False))
        except PermissionError:
            items.append(("  (无权限访问)", cur, False))
        for text, _, _ in items:
            listbox.insert("end", text + "\n")
        listbox.see("1.0")

    def get_line_at_event(event) -> int | None:
        try:
            idx = listbox.index(f"@{event.x},{event.y}")
            return int(idx.split(".")[0])
        except Exception:
            return None

    def on_click(event):
        line = get_line_at_event(event)
        if line and 1 <= line <= len(items):
            listbox.mark_set("insert", f"{line}.0")

    def on_double_click(event):
        line = get_line_at_event(event)
        if line and 1 <= line <= len(items):
            _, path, is_dir = items[line - 1]
            if is_dir:
                refresh_list(path)
            elif path.is_file():
                result[0] = str(path)
                dlg.destroy()

    listbox.bind("<Button-1>", on_click)
    listbox.bind("<Double-1>", on_double_click)

    def select_current():
        try:
            idx = listbox.index("insert")
            line = int(idx.split(".")[0])
            if 1 <= line <= len(items):
                _, path, is_dir = items[line - 1]
                if not is_dir and path.is_file():
                    result[0] = str(path)
                    dlg.destroy()
        except Exception:
            pass

    def go_up():
        cur = Path(path_var.get())
        if cur.parent != cur:
            refresh_list(cur.parent)

    listbox.bind("<Return>", lambda e: select_current())

    btn_frame = ctk.CTkFrame(main, fg_color="transparent")
    btn_frame.pack(fill="x")
    ctk.CTkButton(btn_frame, text="上级目录", width=90, command=go_up).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_frame, text="选择", width=90, command=select_current).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_frame, text="取消", width=90, command=dlg.destroy).pack(side="left", padx=(0, 8))

    refresh_list(initialdir)
    listbox.focus_set()

    dlg.update_idletasks()
    dlg.wait_visibility()
    try:
        dlg.grab_set()
    except Exception:
        pass
    dlg.wait_window()
    return result[0]
