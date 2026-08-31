#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sync_gitee.py — 把本地构建好的 exe 同步到 Gitee Releases（供 GitHub Actions 调用）

用法（环境变量驱动，便于 CI）：
  GITEE_OWNER / GITEE_REPO / GITEE_TOKEN   必填
  VERSION       版本号（形如 1.0.1，不含 v 前缀）
  EXE_PATH      本地 exe 路径
  NOTES         发布说明（可选）
  BRANCH        目标分支（默认 main）

流程：
  POST /releases 建 Release（tag 已存在则 GET /releases/tags/{tag} 复用）
  → multipart 上传 exe 到 /releases/{id}/attach_files
Gitee 附件单文件上限 100MB（本 exe ~57MB 安全）。
"""
import json
import os
import sys
import urllib.request
import urllib.error
import uuid


def _api_post(url, payload, token):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "access_token=" + token,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "CNKI-Sync"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Gitee API {e.code}: {body[:300]}")


def create_release(owner, repo, token, version, notes, branch):
    """创建 Release；若 tag 已存在则复用已有 Release，返回 release id"""
    tag = f"v{version}"
    url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": f"v{version}",
        "body": notes or f"Release v{version}",
        "target_commitish": branch,
        "prerelease": False,
    }
    try:
        data, _ = _api_post(url, payload, token)
        return data["id"]
    except RuntimeError as e:
        if "already exist" in str(e) or "exists" in str(e):
            get_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/tags/{tag}"
            req = urllib.request.Request(
                get_url + "?access_token=" + token,
                headers={"User-Agent": "CNKI-Sync"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))["id"]
        raise


def upload_asset(owner, repo, token, release_id, exe_path):
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
                 "User-Agent": "CNKI-Sync"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    # Windows CI 控制台默认编码可能不支持中文，强制 UTF-8
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    owner = os.environ.get("GITEE_OWNER", "").strip()
    repo = os.environ.get("GITEE_REPO", "").strip()
    token = os.environ.get("GITEE_TOKEN", "").strip()
    version = os.environ.get("VERSION", "").strip()
    exe = os.environ.get("EXE_PATH", "").strip()
    notes = os.environ.get("NOTES", "")
    branch = os.environ.get("BRANCH", "main")

    missing = [n for n, v in (("GITEE_OWNER", owner), ("GITEE_REPO", repo),
                              ("GITEE_TOKEN", token), ("VERSION", version),
                              ("EXE_PATH", exe)) if not v]
    if missing:
        raise SystemExit("缺少环境变量: " + ", ".join(missing))
    if not os.path.exists(exe):
        raise SystemExit(f"未找到 exe: {exe}")

    print(f"[sync] v{version}  owner={owner} repo={repo} exe={exe} ({os.path.getsize(exe)//1024//1024}MB)")
    rid = create_release(owner, repo, token, version, notes, branch)
    print(f"[sync] Release id={rid}，上传 exe ...")
    upload_asset(owner, repo, token, rid, exe)
    print(f"[sync] 完成：exe 已同步到 Gitee Releases v{version}")


if __name__ == "__main__":
    main()
