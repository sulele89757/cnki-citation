#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_release.py — 构建 exe 并发布到 Gitee Releases（支持私有仓库）

流程：
  1. 读取版本号（默认从 cnki_citation.APP_VERSION）
  2. 用 PyInstaller 打包 exe（复用 gui venv）
  3. 调 Gitee API 创建 Release（tag 如 v1.0.1）
  4. 把 exe 作为附件上传（Gitee 单文件上限 100MB，本工具约 57MB 安全）

写权限令牌（与 App 内嵌的只读令牌分开）：
  - 优先读环境变量 GITEE_RELEASE_TOKEN
  - 其次读仓库根目录 .release_token（纯文本，已加入 .gitignore，切勿提交）
  - 都没有则交互式输入

用法：
  python build_release.py                       # 用 APP_VERSION 构建并发布
  python build_release.py --version 1.0.2       # 指定版本
  python build_release.py --notes "修复更新按钮" # 发布说明
  python build_release.py --dry-run             # 只构建不上传
  python build_release.py --skip-build          # 仅发布已有 dist 下的 exe
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EXE_NAME = "CNKI引文工具"
APP_ICON = os.path.join(HERE, "assets", "app.ico")
MAIN_SCRIPT = os.path.join(HERE, "cnki_gui.py")

# ── Gitee 仓库信息（与 cnki_citation.py 保持一致）──
GITEE_OWNER = "sulele"      # TODO
GITEE_REPO = "cnki-citation"         # TODO
GITEE_BRANCH = "main"              # 默认分支（私有库常见为 main）

# 打包用的 Python 解释器：优先 gui venv，否则用当前 python
PYINSTALLER_PYTHON = r"C:/Users/sule/.workbuddy/binaries/python/envs/gui/Scripts/python.exe"
if not os.path.exists(PYINSTALLER_PYTHON):
    PYINSTALLER_PYTHON = sys.executable

GITEE_MAX_ASSET_MB = 100  # Gitee 附件单文件上限


def _read_version():
    """从 cnki_citation.py 读取 APP_VERSION"""
    path = os.path.join(HERE, "cnki_citation.py")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("APP_VERSION"):
                # APP_VERSION = "1.0.0"
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("未在 cnki_citation.py 找到 APP_VERSION")


def _read_token():
    env = os.environ.get("GITEE_RELEASE_TOKEN")
    if env:
        return env.strip()
    tok_file = os.path.join(HERE, ".release_token")
    if os.path.exists(tok_file):
        with open(tok_file, "r", encoding="utf-8") as f:
            t = f.read().strip()
            if t:
                return t
    t = input("请输入 Gitee 写权限个人令牌(PAT)：").strip()
    return t


def _kill_running():
    """结束可能占用 dist 下 exe 的进程，避免覆盖时文件被锁定。

    注意：taskkill.exe 只认单斜杠参数（/IM、/F），双斜杠 //IM 会被当成
    无效参数直接报错退出，且不会杀掉任何进程。
    """
    try:
        subprocess.run(["taskkill", "/IM", EXE_NAME + ".exe", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _safe_deploy(src, dst):
    """把构建产物部署到 dist/。

    直接 open 被占用/正在运行的 exe 时，本机 Windows+Python 组合会抛
    `OSError: [Errno 22] Invalid argument`。规避方式：
      1) 先结束占用进程；
      2) 先复制到临时名（临时名不会被占用），再原子替换目标；
      3) 若目标仍被锁，循环杀进程重试。
    """
    d = os.path.dirname(dst)
    os.makedirs(d, exist_ok=True)
    _kill_running()
    # 若目标是个残留目录（异常情况下），清掉以免 os.replace 失败
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    tmp = dst + ".deploy_tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    # 1) 复制到临时名（临时名未占用，不会触发 Invalid argument）
    shutil.copyfile(src, tmp)
    # 2) 原子替换；目标若被锁则反复杀进程重试
    for _ in range(6):
        try:
            os.replace(tmp, dst)
            return
        except OSError:
            _kill_running()
            time.sleep(1.2)
    # 6 次都失败：清理临时文件（清理失败不应掩盖真正的部署错误）
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except OSError:
        pass
    raise RuntimeError(f"部署失败：无法写入 {dst}，可能被其它进程占用")


def _build_exe():
    """用 PyInstaller 构建单文件 exe 到临时目录，返回产物路径"""
    tmp_build = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "Temp", "cnki_build")
    tmp_dist = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "Temp", "cnki_dist")
    os.makedirs(tmp_build, exist_ok=True)
    os.makedirs(tmp_dist, exist_ok=True)

    cmd = [
        PYINSTALLER_PYTHON, "-m", "PyInstaller",
        "--name", EXE_NAME,
        "--onefile", "--windowed",
        "--icon", APP_ICON,
        "--workpath", tmp_build,
        "--distpath", tmp_dist,
        "--hidden-import", "customtkinter",
        "--hidden-import", "playwright_stealth",
        "--hidden-import", "openpyxl",
        "--hidden-import", "pystray",
        "--collect-all", "playwright",
        "--collect-all", "playwright_stealth",
        "--collect-all", "pystray",
        "--add-data", f"{os.path.join(HERE, 'assets', '批量引文模板.xlsx')};assets",
        "--add-data", f"{os.path.join(HERE, 'assets', 'cnki_icon.png')};assets",
        "--add-data", f"{os.path.join(HERE, 'assets', 'cnki_icon_dark.png')};assets",
        MAIN_SCRIPT,
    ]
    print(f"[构建] 运行 PyInstaller（解释器: {PYINSTALLER_PYTHON}）...")
    subprocess.run(cmd, check=True)

    built = os.path.join(tmp_dist, EXE_NAME + ".exe")
    if not os.path.exists(built):
        raise RuntimeError(f"构建失败：未找到 {built}")
    # 拷回 dist/（处理目标文件被占用的情况）
    final = os.path.join(HERE, "dist", EXE_NAME + ".exe")
    _safe_deploy(built, final)
    print(f"[构建] 完成 -> {final} ({os.path.getsize(final)//1024//1024}MB)")
    return final


def _api_post(url, payload, token):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "access_token=" + token,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "CNKI-Build"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Gitee API {e.code}: {body[:300]}")


def _create_release(owner, repo, token, version, notes):
    """创建 Release；若 tag 已存在则复用已有 Release"""
    tag = f"v{version}"
    url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": f"v{version}",
        "body": notes or f"Release v{version}",
        "target_commitish": GITEE_BRANCH,
        "prerelease": False,
    }
    try:
        data, _ = _api_post(url, payload, token)
        return data["id"]
    except RuntimeError as e:
        if "already exist" in str(e) or "exists" in str(e):
            # 复用已有 tag 对应的 release
            get_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/tags/{tag}"
            req = urllib.request.Request(
                get_url + "?access_token=" + token,
                headers={"User-Agent": "CNKI-Build"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))["id"]
        raise


def _upload_asset(owner, repo, token, release_id, exe_path):
    """multipart 上传 exe 到指定 Release"""
    url = (f"https://gitee.com/api/v5/repos/{owner}/{repo}"
           f"/releases/{release_id}/attach_files?access_token={token}")
    with open(exe_path, "rb") as f:
        file_bytes = f.read()
    boundary = "----CNKIBoundary" + uuid.uuid4().hex
    parts = []
    parts.append(("--" + boundary).encode())
    parts.append(b'\r\nContent-Disposition: form-data; name="access_token"\r\n\r\n')
    parts.append(token.encode())
    parts.append(b"\r\n")
    parts.append(("--" + boundary).encode())
    fn = os.path.basename(exe_path)
    parts.append(f'\r\nContent-Disposition: form-data; name="file"; filename="{fn}"'.encode())
    parts.append(b"\r\nContent-Type: application/octet-stream\r\n\r\n")
    parts.append(file_bytes)
    parts.append(b"\r\n")
    parts.append(("--" + boundary + "--").encode())
    parts.append(b"\r\n")
    body = b"".join(parts)
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "CNKI-Build"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="版本号，默认读 cnki_citation.APP_VERSION")
    ap.add_argument("--notes", default="", help="发布说明(Markdown)")
    ap.add_argument("--dry-run", action="store_true", help="只构建不上传")
    ap.add_argument("--skip-build", action="store_true", help="仅发布 dist 下已有 exe")
    args = ap.parse_args()

    version = args.version or _read_version()
    print(f"[信息] 目标版本 v{version}  owner={GITEE_OWNER} repo={GITEE_REPO}")

    # 1) 构建
    if args.skip_build:
        exe_path = os.path.join(HERE, "dist", EXE_NAME + ".exe")
        if not os.path.exists(exe_path):
            raise SystemExit(f"未找到 {exe_path}，无法 skip-build")
    else:
        exe_path = _build_exe()

    size_mb = os.path.getsize(exe_path) / 1024 / 1024
    if size_mb > GITEE_MAX_ASSET_MB:
        raise SystemExit(f"exe {size_mb:.1f}MB 超过 Gitee {GITEE_MAX_ASSET_MB}MB 上限，无法上传")

    if args.dry_run:
        print(f"[dry-run] 构建成功（{size_mb:.1f}MB），跳过发布。")
        return

    # 2) 发布
    token = _read_token()
    print("[发布] 创建/复用 Release ...")
    rid = _create_release(GITEE_OWNER, GITEE_REPO, token, version, args.notes)
    print(f"[发布] Release id={rid}，上传 exe ...")
    _upload_asset(GITEE_OWNER, GITEE_REPO, token, rid, exe_path)
    print(f"[完成] v{version} 已发布，exe({size_mb:.1f}MB) 已上传到 Gitee Releases。")


if __name__ == "__main__":
    main()
