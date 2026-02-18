#!/bin/bash
# Quick deploy to iPhone
echo "🔨 빌드 중..."
flutter build ios --release 2>&1 | tail -3
echo "📲 설치 중..."
xcrun devicectl device install app --device 92F77DD5-0C39-53C8-9D75-08891F165AB1 build/ios/iphoneos/Runner.app 2>&1 | grep -E "(installed|error|Error)"
echo "🚀 실행 중..."
xcrun devicectl device process launch --device 92F77DD5-0C39-53C8-9D75-08891F165AB1 com.hg6480.dayTrader 2>&1 | grep -E "(Launched|ERROR)"
echo "✅ 완료!"
