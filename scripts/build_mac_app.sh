#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Golf Swing Lab — macOS Native App 打包與安裝腳本
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist_mac"
APP_NAME="Golf Swing Lab.app"
APP_BUNDLE="$DIST_DIR/$APP_NAME"
CONTENTS="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES_DIR="$CONTENTS/Resources"

echo "=== [1/5] 清理舊版建置產物 ==="
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

echo "=== [2/5] 編譯動態可定位 arm64 Mach-O 原生 Launcher ==="
clang -O2 -target arm64-apple-macos11.0 \
    "$REPO_ROOT/launcher.c" \
    -o "$MACOS_DIR/GolfSwingLab"
chmod +x "$MACOS_DIR/GolfSwingLab"

echo "=== [3/5] 建立 Info.plist 與 AppIcon ==="
cat << 'EOF' > "$CONTENTS/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>GolfSwingLab</string>
    <key>CFBundleIdentifier</key>
    <string>com.golfswinglab.desktop</string>
    <key>CFBundleName</key>
    <string>Golf Swing Lab</string>
    <key>CFBundleDisplayName</key>
    <string>Golf Swing Lab</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
</dict>
</plist>
EOF

# 若有圖示則拷貝
if [ -f "$REPO_ROOT/dist_mac/AppIcon.icns" ]; then
    cp "$REPO_ROOT/dist_mac/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
elif [ -f "/Users/mathew/Desktop/Golf Swing Lab.app/Contents/Resources/AppIcon.icns" ]; then
    cp "/Users/mathew/Desktop/Golf Swing Lab.app/Contents/Resources/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
fi

echo "=== [4/5] 執行 macOS 本地 Ad-hoc 程式碼簽名 ==="
codesign -s - --force --deep "$APP_BUNDLE"

echo "=== [5/5] 同步部署至系統 /Applications 與桌面 ==="
rm -rf "/Applications/$APP_NAME" "$HOME/Desktop/$APP_NAME"
cp -R "$APP_BUNDLE" "/Applications/$APP_NAME"
cp -R "$APP_BUNDLE" "$HOME/Desktop/$APP_NAME"

# 註冊至 LaunchServices
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f -R -trusted "/Applications/$APP_NAME" "$HOME/Desktop/$APP_NAME" || true

echo "✅ Golf Swing Lab Mac 原生桌面 App 建置完成！"
echo "   - 應用程式路徑: /Applications/$APP_NAME"
echo "   - 桌面快捷路徑: $HOME/Desktop/$APP_NAME"
