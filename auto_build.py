#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
auto_build.py — 仓库有更新时自动构建并发布 exe 到 Gitee Releases

原理（无需公网 IP / 无需 Gitee Go）：
  每隔 POLL_INTERVAL 秒，用 Gitee API 查默认分支最新 commit SHA；
  若与本地记录的 .last_commit 不同，说明代码已更新，则自动调用 build_release.py
  完成「构建 + 建 Release + 上传 exe」。

令牌：读 GITEE_RELEASE_TOKEN 环境变量或仓库根 .release_token（写令牌可兼读）。
      若只用只读令牌也够轮询，可单独配置。

用法：
  python auto_build.py                 # 每 5 分钟轮询一次（前台常驻）
  python auto_build.py --interval 120  # 每 2 分钟
  python auto_build.py --once          # 只检查一次（适合用 Windows 任务计划程序定时跑）
  python auto_build.py --force         # 无视记录，立即构建发布一次

建议：用 Windows「任务计划程序」设置「登录时启动」，或 --once 配「每隔 N 分钟」触发器，
即可实现「推送代码 -> 自动出 exe 并发布 Release」。
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
LAST_COMMIT_FILE = os.path.join(HERE, ".last_commit")

GITEE_OWNER = "sulele"   # TODO: 与 build_release.py 一致
GITEE_REPO = "cnki-citation"      # TODO
GITEE_BRANCH = "main"           # 默认分支
POLL_INTERVAL = 300               # 秒


def _read_token():
    env = os.environ.get("GITEE_RELEASE_TOKEN")
    if env:
        return env.strip()
    tok_file = os.path.join(HERE, ".release_token")
    if os.path.exists(tok_file):
        with open(tok_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _latest_commit_sha(token):
    url = (f"https://gitee.com/api/v5/repos/{GITEE_OWNER}/{GITEE_REPO}/commits"
           f"?sha={GITEE_BRANCH}&per_page=1")
    if token:
        url += "&access_token=" + token
    req = urllib.request.Request(url, headers={"User-Agent": "CNKI-AutoBuild"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = __import__("json").loads(resp.read().decode("utf-8"))
    if isinstance(data, list) and data:
        return data[0].get("sha")
    return None


def _read_last():
    if os.path.exists(LAST_COMMIT_FILE):
        with open(LAST_COMMIT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _write_last(sha):
    with open(LAST_COMMIT_FILE, "w", encoding="utf-8") as f:
        f.write(sha or "")


def _run_build(notes):
    print(f"[{_now()}] 代码已更新，开始自动构建并发布 ...")
    cmd = [sys.executable, os.path.join(HERE, "build_release.py")]
    if notes:
        cmd += ["--notes", notes]
    try:
        subprocess.run(cmd, check=True, cwd=HERE)
        print(f"[{_now()}] 自动发布完成。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[{_now()}] 构建/发布失败: {e}", file=sys.stderr)
        return False


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=POLL_INTERVAL)
    ap.add_argument("--once", action="store_true", help="只检查一次即退出")
    ap.add_argument("--force", action="store_true", help="立即构建发布一次")
    ap.add_argument("--notes", default="", help="发布说明")
    args = ap.parse_args()

    token = _read_token()
    print(f"[{_now()}] auto_build 启动：监听 {GITEE_OWNER}/{GITEE_REPO}@{GITEE_BRANCH}")
    if not token:
        print("[警告] 未检测到令牌（GITEE_RELEASE_TOKEN / .release_token），"
              "公开仓库可轮询，私有仓库将无法访问。", file=sys.stderr)

    if args.force:
        _run_build(args.notes)
        return

    while True:
        try:
            sha = _latest_commit_sha(token)
            last = _read_last()
            if sha and sha != last:
                print(f"[{_now()}] 检测到新提交 {sha[:8]}（上次 {last[:8] or '无'}）")
                if _run_build(args.notes):
                    _write_last(sha)
            else:
                print(f"[{_now()}] 无变化（最新 {sha[:8] if sha else 'N/A'}）")
        except Exception as e:
            print(f"[{_now()}] 轮询出错: {e}", file=sys.stderr)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
