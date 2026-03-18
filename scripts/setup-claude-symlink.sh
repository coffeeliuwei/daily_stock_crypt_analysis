#!/bin/bash
# ===================================
# CLAUDE.md 符号链接设置脚本
# ===================================
# 在 Linux/Mac 环境中运行此脚本，将 CLAUDE.md 设置为指向 AGENTS.md 的符号链接
#
# 用法：
#   chmod +x scripts/setup-claude-symlink.sh
#   ./scripts/setup-claude-symlink.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLAUDE_MD="$PROJECT_ROOT/CLAUDE.md"
AGENTS_MD="$PROJECT_ROOT/AGENTS.md"

echo "=== CLAUDE.md 符号链接设置 ==="
echo "项目根目录: $PROJECT_ROOT"

# 检查 AGENTS.md 是否存在
if [ ! -f "$AGENTS_MD" ]; then
    echo "错误: AGENTS.md 不存在于 $AGENTS_MD"
    exit 1
fi

# 删除现有的 CLAUDE.md（如果是文件）
if [ -f "$CLAUDE_MD" ] && [ ! -L "$CLAUDE_MD" ]; then
    echo "删除现有 CLAUDE.md 文件..."
    rm "$CLAUDE_MD"
fi

# 如果已经是符号链接，先删除
if [ -L "$CLAUDE_MD" ]; then
    echo "删除现有符号链接..."
    rm "$CLAUDE_MD"
fi

# 创建新的符号链接
echo "创建符号链接: CLAUDE.md -> AGENTS.md"
ln -s AGENTS.md "$CLAUDE_MD"

# 验证
if [ -L "$CLAUDE_MD" ]; then
    echo "✅ 符号链接创建成功"
    ls -la "$CLAUDE_MD"
else
    echo "❌ 符号链接创建失败"
    exit 1
fi

echo ""
echo "完成！CLAUDE.md 现在是 AGENTS.md 的符号链接。"