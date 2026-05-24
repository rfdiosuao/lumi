#!/bin/bash
set -e

echo "======================================"
echo "OpenClaw 授权服务新版本部署脚本"
echo "======================================"
echo ""

cd /opt/openclaw-license

# 1. 备份现网文件
echo "[1/6] 备份现网 server.py..."
ts=$(date -u +%Y%m%d%H%M%S)
cp server.py "server.py.bak-$ts"
echo "已备份: server.py.bak-$ts"
echo ""

# 2. 显示新文件内容（手动复制时跳过）
echo "[2/6] 请将新的 server.py 内容保存到 /tmp/openclaw-license-server.py"
echo "然后按回车继续..."
read -r

# 3. 校验文件
echo "[3/6] 校验新文件..."
sha256sum /tmp/openclaw-license-server.py
echo ""
echo "Python 语法检查..."
python3 -m py_compile /tmp/openclaw-license-server.py
echo "语法检查通过"
echo ""

# 4. 覆盖上线
echo "[4/6] 部署新版本..."
install -m 0644 /tmp/openclaw-license-server.py /opt/openclaw-license/server.py
echo "已覆盖 server.py"
echo ""

# 5. 重启服务
echo "[5/6] 重启 openclaw-license 服务..."
systemctl restart openclaw-license
echo "服务已重启"
echo ""

# 6. 验证
echo "[6/6] 验证服务..."
sleep 2
echo ""
echo "健康检查:"
curl -fsS http://127.0.0.1:18791/health
echo ""
echo ""
echo "激活接口测试（期待返回 '授权码不存在'）:"
curl -sS -X POST http://127.0.0.1:18791/api/member/activate \
  -H 'Content-Type: application/json' \
  -d '{"code":"INVALID-SMOKE","installId":"smoke","deviceId":"smoke"}'
echo ""
echo ""

# 检查关键文件
echo "关键文件检查:"
echo "license.db: $( [ -f license.db ] && echo "存在" || echo "不存在" )"
echo "private_key.b64: $( [ -f private_key.b64 ] && echo "存在" || echo "不存在" )"
echo "admin_token.txt: $( [ -f admin_token.txt ] && echo "存在" || echo "不存在" )"
echo ""
echo "服务状态:"
systemctl is-active openclaw-license
echo ""
echo "======================================"
echo "部署完成！"
echo "======================================"