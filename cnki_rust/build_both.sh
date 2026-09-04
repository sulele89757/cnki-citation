#!/usr/bin/env bash
# 同时产出两种 WebView2 分发形态的 NSIS 安装包：
#   - offline : 内置完整 WebView2，用户离线可装 (offlineInstaller)
#   - lite    : 安装时由用户机器联网拉取 WebView2 (embedBootstrapper)
# 用法: bash build_both.sh   (在 cnki_rust 目录执行)
set -euo pipefail
cd "$(dirname "$0")"

CONF="src-tauri/tauri.conf.json"
OUT="dist-release"
mkdir -p "$OUT"

VER=$(node -e "const fs=require('fs');process.stdout.write(JSON.parse(fs.readFileSync(process.argv[1],'utf8')).version)" "$CONF")

set_mode() {
  node -e "const fs=require('fs');const p=process.argv[1],m=process.argv[2];const d=JSON.parse(fs.readFileSync(p,'utf8'));d.bundle.windows.webviewInstallMode.type=m;fs.writeFileSync(p,JSON.stringify(d,null,2)+'\n');" "$CONF" "$1"
}

if cargo tauri --version >/dev/null 2>&1; then BUILD=(cargo tauri build)
elif [ -f package.json ]; then BUILD=(npm run tauri build)
else echo "未找到 tauri 构建方式"; exit 1; fi

build() {
  local mode="$1" label="$2"
  echo "==> 构建 webviewInstallMode=$mode"
  set_mode "$mode"
  "${BUILD[@]}"
  local inst
  inst=$(ls src-tauri/target/release/bundle/nsis/*.exe 2>/dev/null | head -1)
  [ -n "$inst" ] || { echo "未找到安装包 ($mode)"; exit 1; }
  cp "$inst" "$OUT/CNKI-Citation-Tool-${VER}-${label}.exe"
  echo "    -> $OUT/CNKI-Citation-Tool-${VER}-${label}.exe"
}

build offlineInstaller offline
build embedBootstrapper lite
set_mode offlineInstaller   # 恢复安全默认，单构建也为内置版
echo "完成。两种安装包位于 $OUT/"
