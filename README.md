# startupdisk - Linux 下 Windows 启动盘制作工具

在 Linux 系统上制作 Windows 10/11 UEFI 启动盘的命令行工具。支持 `install.wim` 大于 4GB 的镜像，通过 [UEFI:NTFS](https://github.com/pbatard/uefi-ntfs) 实现从 NTFS 分区 UEFI 启动。

## 系统要求

- Linux（已测试 Ubuntu、Debian、Fedora）
- Python 3.10+
- 需 root 权限（操作块设备）

### 依赖包（Ubuntu/Debian）

```bash
sudo apt install parted ntfs-3g python3-tk
```

## 安装

### 使用 Pipenv（推荐）

```bash
cd /home/gezhipeng/workspace/startupdisk
pipenv install
```

### 或使用 pip

```bash
pip install -e .
```

GUI 依赖：`customtkinter`（Pipfile / pyproject.toml 已包含）

## 使用方法

### 1. 图形界面（推荐）

```bash
# Pipenv
sudo pipenv run python -m startupdisk gui

# 或 pip
sudo python -m startupdisk gui
```

**一键安装**：界面提供「一键安装 Python 依赖」和「一键安装系统依赖」按钮，首次使用可点击安装缺失依赖。

### 2. 列出可用 U 盘

```bash
python -m startupdisk list
```

### 3. 命令行制作启动盘

```bash
# 需使用 sudo
sudo python -m startupdisk create -i /path/to/Win11.iso -d /dev/sdb
```

参数说明：
- `-i, --iso`：Windows ISO 文件路径
- `-d, --device`：目标 USB 设备（如 `/dev/sdb`）
- `--uefi-ntfs`：可选，指定 UEFI:NTFS 镜像路径（不指定则自动从 GitHub 下载）
- `-y, --yes`：跳过确认提示

### 示例

```bash
# 列出 U 盘
python -m startupdisk list

# 制作启动盘（带确认）
sudo python -m startupdisk create -i ~/Downloads/Win11_24H2.iso -d /dev/sdb

# 跳过确认
sudo python -m startupdisk create -i Win11.iso -d /dev/sdb -y
```

## 工作原理

1. **分区布局**：创建 GPT 分区表，主分区为 NTFS（存放 Windows 安装文件），末尾小分区用于 UEFI:NTFS 引导
2. **UEFI:NTFS**：自动下载或使用指定的 UEFI:NTFS 镜像，使 UEFI 能从 NTFS 分区启动
3. **文件复制**：挂载 ISO 和 U 盘 NTFS 分区，复制全部文件到 U 盘

## 注意事项

- ⚠️ **数据将被清除**：制作前会格式化目标设备，请确认选择的是正确的 U 盘
- 建议 U 盘容量 ≥ 8GB（Windows 11 推荐 16GB）
- 支持 Secure Boot 的 UEFI:NTFS `_signed` 版本需从 [uefi-ntfs](https://github.com/pbatard/uefi-ntfs/releases) 下载并手动指定
- 如无法访问 GitHub，可手动下载 `uefi-ntfs_x64.img` 到 `~/.cache/startupdisk/` 或通过 `--uefi-ntfs` 指定

## 许可证

MIT
