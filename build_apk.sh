#!/usr/bin/env bash
set -e

echo "=========================================="
echo "Building Deriv Bot Android APK..."
echo "=========================================="

# Ensure gradlew executable
chmod +x ./gradlew

# Execute assembleDebug task
./gradlew assembleDebug

APK_PATH="app/build/outputs/apk/debug/app-debug.apk"

if [ -f "$APK_PATH" ]; then
    cp "$APK_PATH" ./app-debug.apk
    echo "=========================================="
    echo "BUILD SUCCESSFUL!"
    echo "APK generated at:"
    echo "  1) $APK_PATH"
    echo "  2) ./app-debug.apk"
    echo "File Size: $(du -h app-debug.apk | cut -f1)"
    echo "=========================================="
else
    echo "[-] Error: APK file not found at expected location."
    exit 1
fi
