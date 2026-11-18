#!/bin/bash
# 康神语录 bot — Mac 一键启动
# 第一次运行会装依赖（需要联网），之后双击即可。
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "第一次启动：正在创建环境并安装依赖，大概 1-2 分钟…"
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
# 每次启动都补装一遍依赖 (已装的会秒过), 保证更新生效
.venv/bin/pip install -q -r requirements.txt
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "⚠️ 没找到 ffmpeg（语音播放需要它）。如果装了 Homebrew，运行：brew install ffmpeg"
fi
if [ -z "$DISCORD_TOKEN" ]; then
  echo "请粘贴 bot 的 token（粘贴时屏幕不显示，输完按回车）："
  read -s DISCORD_TOKEN
  export DISCORD_TOKEN
fi
# 修 macOS 版 Python 找不到证书的问题（CERTIFICATE_VERIFY_FAILED）
SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())' 2>/dev/null)"
[ -n "$SSL_CERT_FILE" ] && export SSL_CERT_FILE
echo "正在启动康神语录 bot… 关掉这个窗口或按 Ctrl+C 就停。"
.venv/bin/python bot.py
