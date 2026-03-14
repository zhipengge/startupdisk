#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

command -v pipenv >/dev/null 2>&1 || {
    echo "需要 pipenv。请先执行: pip install pipenv"
    exit 1
}

# 无 .venv 或依赖缺失时安装
if [ ! -d ".venv" ]; then
    echo "首次运行，正在创建环境并安装依赖..."
    pipenv install || exit 1
elif ! .venv/bin/python -c "import customtkinter; from PIL import Image" 2>/dev/null; then
    echo "正在补全依赖..."
    pipenv install || exit 1
fi

# GUI 以当前用户运行（避免 sudo 下 venv 导入问题），制作时自动请求 root
exec "$ROOT/.venv/bin/python" -m startupdisk gui
