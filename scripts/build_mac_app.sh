#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Golf Swing Lab R4 — macOS Native App 安全打包、驗證、備份與原子安裝腳本
# 安全契約：
# 1. 絕不刪除使用者桌面 ($HOME/Desktop) 任何檔案或目錄
# 2. 絕不觸碰或清除 ~/.golfswinglab/storage、session_secret 或模型目錄
# 3. 覆寫 /Applications/Golf Swing Lab.app 前強制驗證 CFBundleIdentifier
# 4. 自動備份既有 App Bundle 至 ~/.golfswinglab/backups/app_bundles，並支援 --rollback
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist_mac"
APP_NAME="Golf Swing Lab.app"
EXPECTED_BUNDLE_ID="com.golfswinglab.desktop"
APP_BUNDLE="$DIST_DIR/$APP_NAME"
TARGET_APP="/Applications/$APP_NAME"
BACKUP_ROOT="$HOME/.golfswinglab/backups/app_bundles"
CONTENTS="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES_DIR="$CONTENTS/Resources"

mkdir -p "$BACKUP_ROOT"

if [ "${1:-}" = "--rollback" ]; then
    LATEST_BACKUP="$(ls -dt "$BACKUP_ROOT"/Golf_Swing_Lab_*.app 2>/dev/null | head -n 1 || true)"
    if [ -z "$LATEST_BACKUP" ] || [ ! -d "$LATEST_BACKUP" ]; then
        echo "❌ 找不到可用的 App Bundle 備份於: $BACKUP_ROOT" >&2
        exit 1
    fi
    echo "=== 正在從備份還原: $LATEST_BACKUP -> $TARGET_APP ==="
    rm -rf "$TARGET_APP"
    cp -R "$LATEST_BACKUP" "$TARGET_APP"
    echo "✅ 已成功還原舊版 /Applications/$APP_NAME"
    exit 0
fi

echo "=== [1/6] 準備乾淨建置暫存區 ($DIST_DIR) ==="
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

echo "=== [2/6] 編譯動態可定位 arm64 Mach-O 原生 Launcher ==="
clang -O2 -target arm64-apple-macos11.0 \
    "$REPO_ROOT/launcher.c" \
    -o "$MACOS_DIR/GolfSwingLab"
chmod +x "$MACOS_DIR/GolfSwingLab"

echo "=== [3/6] 建立 Info.plist (v1.4.0 R4 Tracer Studio) 與 AppIcon ==="
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
    <string>1.4.0</string>
    <key>CFBundleVersion</key>
    <string>4</string>
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

# 複製圖示
if [ -f "$REPO_ROOT/assets/AppIcon.icns" ]; then
    cp "$REPO_ROOT/assets/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
elif [ -f "$TARGET_APP/Contents/Resources/AppIcon.icns" ]; then
    cp "$TARGET_APP/Contents/Resources/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
fi

echo "=== [4/6] 執行 macOS 本地 Ad-hoc 程式碼簽名與驗證 ==="
codesign -s - --force --deep "$APP_BUNDLE"
codesign --verify --deep --strict "$APP_BUNDLE"

echo "=== [5/6] 驗證既有 /Applications/$APP_NAME 並建立安全備份 ==="
if [ -d "$TARGET_APP" ]; then
    EXISTING_PLIST="$TARGET_APP/Contents/Info.plist"
    if [ -f "$EXISTING_PLIST" ]; then
        EXISTING_ID="$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$EXISTING_PLIST" 2>/dev/null || echo "")"
        if [ -n "$EXISTING_ID" ] && [ "$EXISTING_ID" != "$EXPECTED_BUNDLE_ID" ]; then
            echo "❌ 安全攔截：目標路徑 $TARGET_APP 之 CFBundleIdentifier ($EXISTING_ID) 與預期 ($EXPECTED_BUNDLE_ID) 不符，拒絕覆寫！" >&2
            exit 1
        fi
    fi
    BACKUP_PATH="$BACKUP_ROOT/Golf_Swing_Lab_$(date +%Y%m%d_%H%M%S).app"
    rm -rf "$BACKUP_ROOT"/Golf_Swing_Lab_*.app
    cp -R "$TARGET_APP" "$BACKUP_PATH"
    echo "   - 已備份既有 App Bundle 至: $BACKUP_PATH"
fi

echo "=== [6/6] 原子安裝至 /Applications/$APP_NAME ==="
STAGED_APP="/Applications/.Golf_Swing_Lab_staging_$$.app"
rm -rf "$STAGED_APP"
cp -R "$APP_BUNDLE" "$STAGED_APP"
rm -rf "$TARGET_APP"
mv "$STAGED_APP" "$TARGET_APP"

# 清理 dist_mac 臨時建置目錄（絕不觸碰使用者桌面或 ~/.golfswinglab/storage）
rm -rf "$DIST_DIR"

# 註冊至 macOS LaunchServices
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f -R -trusted "$TARGET_APP" || true

echo "✅ Golf Swing Lab R4 (v1.4.0) Mac 原生桌面 App 安全更新完成！"
echo "   - 正式應用程式路徑: $TARGET_APP"
echo "   - 如需回滾舊版請執行: bash scripts/build_mac_app.sh --rollback"
