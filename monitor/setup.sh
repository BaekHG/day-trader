#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 데이트레이더 모니터 설치 ==="

python3 -m venv "$SCRIPT_DIR/venv"
source "$SCRIPT_DIR/venv/bin/activate"
pip install -r "$SCRIPT_DIR/requirements.txt"

mkdir -p "$SCRIPT_DIR/logs"

cp "$SCRIPT_DIR/com.daytrader.monitor.plist" ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.daytrader.monitor.plist

echo "설치 완료!"
echo ""
echo "사용법:"
echo "  수동 실행: $SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/main.py"
echo "  자동 시작: 평일 08:55 KST 자동 실행됩니다"
echo ""
echo ".env 파일에 텔레그램 설정을 추가하세요:"
echo "  TELEGRAM_BOT_TOKEN=your_token"
echo "  TELEGRAM_CHAT_ID=your_chat_id"
