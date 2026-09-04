#!/usr/bin/env bash
# 构建 Tauri NSIS 安装包（仅 embedBootstrapper 形态）：
#   安装时由用户机器联网拉取 WebView2（轻量，~6.6MB）。
# 不再提供内置 WebView2 的 offline 版本（构建/推送 Gitee 过慢，改用官方下载链接）。
# 用法: bash build_both.sh   (在 rust 目录执行)
# 产物保留 NSIS 默认命名：dist/CNKI_<版本>_x64-setup.exe
set -euo pipefail
cd "$(dirname "$0")"

CONF="src-tauri/tauri.conf.json"
OUT="dist"
mkdir -p "$OUT"

VER=$(node -e "const fs=require('fs');process.stdout.write(JSON.parse(fs.readFileSync(process.argv[1],'utf8')).version)" "$CONF")

set_mode() {
  node -e "const fs=require('fs');const p=process.argv[1],m=process.argv[2];const d=JSON.parse(fs.readFileSync(p,'utf8'));d.bundle.windows.webviewInstallMode.type=m;fs.writeFileSync(p,JSON.stringify(d,null,2)+'\n');" "$CONF" "$1"
}

if cargo tauri --version >/dev/null 2>&1; then BUILD=(cargo tauri build)
elif [ -f package.json ]; then BUILD=(npm run tauri build)
else echo "未找到 tauri 构建方式"; exit 1; fi

echo "==> 构建 webviewInstallMode=embedBootstrapper (VER=$VER)"
set_mode embedBootstrapper
"${BUILD[@]}"
inst=$(ls src-tauri/target/release/bundle/nsis/*.exe 2>/dev/null | head -1)
[ -n "$inst" ] || { echo "未找到安装包"; exit 1; }
# 保留 NSIS 默认命名 CNKI_<版本>_x64-setup.exe，仅落到 dist/ 便于统一分发
cp "$inst" "$OUT/CNKI_${VER}_x64-setup.exe"
echo "    -> $OUT/CNKI_${VER}_x64-setup.exe"
echo "完成。"
