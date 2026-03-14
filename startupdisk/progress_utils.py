"""
进度条、写入速度、剩余时间的统一逻辑
参考 tqdm (https://github.com/tqdm/tqdm) 的双 EMA 实现，平滑瞬时速度波动
"""

import time


class EMA:
    """
    指数移动平均，用于平滑速度估计
    参考 tqdm：对 delta_bytes 和 delta_time 分别做 EMA，再计算 rate = ema_dn / ema_dt
    """

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.last = 0.0
        self.calls = 0

    def update(self, x: float) -> float:
        beta = 1 - self.alpha
        self.last = self.alpha * x + beta * self.last
        self.calls += 1
        # 偏差校正：早期迭代时 last 偏小
        return self.last / (1 - beta**self.calls) if self.calls > 0 else self.last

    def value(self) -> float:
        return self.last


class SpeedEstimator:
    """
    写入速度与 ETA 估计器
    使用双 EMA（distance + time）计算平滑速度，避免瞬时波动导致 ETA 剧烈跳动
    """

    def __init__(self, alpha: float = 0.3):
        self._ema_dn = EMA(alpha)  # delta bytes
        self._ema_dt = EMA(alpha)  # delta time (seconds)
        self._last_bytes: int | None = None
        self._last_time: float | None = None
        self._speed_mbs: float = 0.0

    def update(self, bytes_copied: int) -> float:
        """
        传入当前已复制字节数，更新内部 EMA 并返回平滑后的 speed_mbs
        """
        now = time.monotonic()
        if self._last_bytes is not None and self._last_time is not None:
            dn = bytes_copied - self._last_bytes
            dt = now - self._last_time
            if dt > 0.05 and dn > 0:  # 仅有实际进度时才更新 EMA，避免无进度时拉低速度
                ema_dn = self._ema_dn.update(float(dn))
                ema_dt = self._ema_dt.update(dt)
                if ema_dt > 1e-9:
                    self._speed_mbs = ema_dn / ema_dt / (1024 * 1024)
        self._last_bytes = bytes_copied
        self._last_time = now
        return self._speed_mbs

    def get_speed_mbs(self) -> float:
        return self._speed_mbs

    def get_remaining_sec(self, total_bytes: int, bytes_copied: int) -> float:
        if self._speed_mbs <= 0 or total_bytes <= bytes_copied:
            return -1.0
        remaining = total_bytes - bytes_copied
        return remaining / (self._speed_mbs * 1024 * 1024)


def format_speed(speed_mbs: float) -> str:
    """格式化速度，低速度时保留更多小数位"""
    if speed_mbs <= 0:
        return "-- MB/s"
    if speed_mbs < 0.1:
        return f"{speed_mbs:.2f} MB/s"
    if speed_mbs < 100:
        return f"{speed_mbs:.1f} MB/s"
    return f"{speed_mbs:.0f} MB/s"


def format_eta(remaining_sec: float) -> str:
    """
    格式化剩余时间
    参考 tqdm format_interval: [H:]MM:SS
    超过 24 小时显示「较久」
    """
    if remaining_sec < 0:
        return "--"
    if remaining_sec > 24 * 3600:
        return "较久，请耐心等待"
    s = int(remaining_sec)
    mins, sec = divmod(s, 60)
    h, m = divmod(mins, 60)
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def format_eta_friendly(remaining_sec: float) -> str:
    """中文友好格式：约 X 分 X 秒"""
    if remaining_sec < 0:
        return "--"
    if remaining_sec > 24 * 3600:
        return "较久，请耐心等待"
    s = int(remaining_sec)
    if s < 60:
        return f"约 {s} 秒"
    mins, sec = divmod(s, 60)
    if mins < 60:
        return f"约 {mins} 分 {sec} 秒"
    h, m = divmod(mins, 60)
    return f"约 {h} 时 {m} 分"
