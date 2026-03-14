# 进度数据获取架构

## 问题分析

原先存在两套完全不同的数据获取方式，易导致行为不一致：

| 路径 | 数据来源 | 更新方式 | 问题 |
|------|----------|----------|------|
| root 直接调用 | 内存 dict | 同步回调 + 120ms 轮询 | 与 pkexec 路径逻辑分裂 |
| pkexec 子进程 | stdout 管道 | 逐行解析 `[PROGRESS]` | 受缓冲、管道容量影响 |

## 统一方案（已实现）

**核心思路**：所有场景都通过 **子进程 + 标准输出协议** 获取进度，与 rsync、dd status=progress、pv 等工具类似。

### 数据流

```
Writer (copy_iso_to_usb)
    │ progress_callback(bc, tb)
    ▼
CLI (cmd_create)
    │ sys.stdout.reconfigure(line_buffering=True)  # 非 TTY 时强制行缓冲
    │ print("[PROGRESS]{bc},{tb}", flush=True)
    ▼
stdout 管道
    │ python -u, PYTHONUNBUFFERED=1, bufsize=1    # 多重保障避免缓冲
    ▼
GUI _run_create_subprocess
    │ for line in proc.stdout
    │ 解析 [PROGRESS] → SpeedEstimator → _display_progress
    ▼
主线程 after(0) 回调
```

### 协议格式

- 进度行：`[PROGRESS]<bytes_copied>,<total_bytes>`
- 其他行：日志，直接追加到刷写日志

### 实现要点

1. **统一子进程**：root 与非 root 均通过 `_run_create_subprocess`，仅命令行前缀不同（root 无 pkexec）
2. **缓冲控制**：`python -u`、`PYTHONUNBUFFERED=1`、CLI 内 `reconfigure(line_buffering=True)`、`bufsize=1`
3. **速度平滑**：`progress_utils.SpeedEstimator` 双 EMA（参考 tqdm）

### 参考

- [tqdm EMA](https://github.com/tqdm/tqdm) - 双 EMA 速度估计
- [Python subprocess 实时输出](https://stackoverflow.com/questions/54091396/live-output-stream-from-python-subprocess)
