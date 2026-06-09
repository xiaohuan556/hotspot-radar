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
python3 -m pip install PyQt6 openai flask

# 设置 .env 配置
if [ ! -f .env ]; then
    echo ""
    echo ">>> 请配置 API Key（在 .env 文件中填写）："
    cat > .env << 'EOF'
# 热点雷达 API 配置
# 请替换以下占位符为你的真实 API Key

OPENAI_API_KEY="sk-your-deepseek-api-key"
OPENAI_BASE_URL="https://api.deepseek.com/v1"
LLM_MODEL="deepseek-chat"

# 以下为可选配置（不填则对应功能不可用）
YOUTUBE_API_KEY=""
TMDB_API_KEY=""
NEWSAPI_KEY=""
EOF
    echo "   .env 已创建，请编辑填写 API Key 后重新启动"
fi

echo ""
echo "✅ 安装完成！"
echo "   Web版：python3 app.py"
echo "   桌面版：python3 main.py"
echo ""
