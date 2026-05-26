#!/bin/bash
# 热点雷达 macOS 一键安装
# 用法：终端里 cd 到这个文件夹，然后 bash install.sh

echo "📡 热点雷达 - 安装中..."

# 检查 Homebrew（Mac 包管理器）
if ! command -v brew &>/dev/null; then
    echo ">>> 安装 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# 安装 Python3
if ! command -v python3 &>/dev/null; then
    echo ">>> 安装 Python3..."
    brew install python3
fi

# 安装依赖
echo ">>> 安装 Python 依赖..."
python3 -m pip install PyQt6 openai

# 复制 .env 配置（如果存在）
if [ ! -f .env ]; then
    echo "# 热点雷达 API 配置" > .env
    echo 'OPENAI_API_KEY="sk-2b1544c282cd44709b2408745f77726c"' >> .env
    echo 'OPENAI_BASE_URL="https://api.deepseek.com/v1"' >> .env
    echo 'LLM_MODEL="deepseek-chat"' >> .env
    echo 'YOUTUBE_API_KEY="AIzaSyAFsEN9EiBrn9mZzmh3Yl1fMIdBCZMv8FM"' >> .env
    echo 'TMDB_API_KEY="9f842807e0c4919d22ad8903bbd210a4"' >> .env
    echo 'NEWSAPI_KEY="3bd17c719f174ce797556f31ffe01f64"' >> .env
    echo 'TRENDMCP_KEY="tmcp_live_vj4mz9ctf815ne95yjnuwhstups8eh0c"' >> .env
fi

echo ""
echo "✅ 安装完成！运行："
echo "   python3 main.py"
echo ""
