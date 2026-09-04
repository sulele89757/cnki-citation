#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sync_gitee.py — 把本地构建好的 exe 同步到 Gitee Releases（供 GitHub Actions 调用）

用法（环境变量驱动，便于 CI）：
  GITEE_OWNER / GITEE_REPO / GITEE_TOKEN       必填
  VERSION       版本号（形如 1.0.1，不含 v 前缀）
  待上传文件（可任选其一或多个）：
    EXE_PATH              单文件路径
    EXE_PATH_RS           Tauri NSIS 安装包（CNKI-rs-installer.exe，embedBootstrapper）
    EXE_PATH_PYTHON       Python 版 exe（现已不再构建，仅保留兼容）
    EXE_PATH_RUST         Rust 裸 exe（向后兼容）
  NOTES         发布说明（可选）
  BRANCH        目标分支（默认 main）

流程：
  POST /releases 建 Release（tag 已存在则 GET /releases/tags/{tag} 复用）
  → multipart 上传 exe 到 /releases/{id}/attach_files
Gitee 附件单文件上限 100MB；Rust 安装包（CNKI-rs-installer.exe，~6.6MB）远小于上限，
直接整包上传即可（不再提供内置 WebView2 的离线版，故无需分卷与自合并引导器）。
"""
import json
import os
import sys
import time
import http.client
import urllib.request
import urllib.error
import urllib.parse
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
        # 创建失败（tag 已存在 / 名称被占用 / 其它）——尝试按 tag 复用已有 Release。
        # Gitee 重复报错可能是中文（"已存在"），无法靠英文子串命中，故统一走 GET 兜底。
        print(f"[sync] 创建 Release 失败（{e}），尝试按 tag 复用已有 Release ...", flush=True)
        try:
            get_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases/tags/{tag}"
            req = urllib.request.Request(
                get_url + "?access_token=" + token,
                headers={"User-Agent": "CNKI-Sync"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))["id"]
        except Exception as e2:
            raise RuntimeError(
                f"无法创建或复用 Release v{version}: 创建失败={e} | 复用失败={e2}")


def _list_assets(owner, repo, token, release_id):
    """列出 Release 已有附件，返回 [(name, size), ...]；失败返回空列表（不阻断上传）"""
    url = (f"https://gitee.com/api/v5/repos/{owner}/{repo}"
           f"/releases/{release_id}/attach_files?access_token={token}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CNKI-Sync"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = []
        for it in data if isinstance(data, list) else []:
            n = it.get("name") or it.get("title") or it.get("filename")
            s = it.get("size") or it.get("bytes") or it.get("byte_size")
            if n and s is not None:
                out.append((str(n), int(s)))
        return out
    except Exception as e:
        print(f"[sync] 检查已有附件失败（忽略，继续上传）: {e}")
        return []


def upload_asset(owner, repo, token, release_id, exe_path, max_retries=3):
    """multipart 分块流式上传 exe 到指定 Release。
    - 已存在同名同大小附件则跳过（重跑不重复）
    - 分 1MB 块发送，超时 600s，整体慢链路上也不会因单次 sendall 超时
    - 失败自动重试（指数退避）
    """
    fn = os.path.basename(exe_path)
    fsize = os.path.getsize(exe_path)

    # 去重：同名同大小已存在则跳过
    try:
        for n, s in _list_assets(owner, repo, token, release_id):
            if n == fn and s == fsize:
                print(f"[sync] 已存在同名同大小附件 {fn}（{fsize//1024//1024}MB），跳过上传")
                return {"skipped": True, "name": fn}
    except Exception:
        pass

    url = (f"https://gitee.com/api/v5/repos/{owner}/{repo}"
           f"/releases/{release_id}/attach_files?access_token={token}")
    with open(exe_path, "rb") as f:
        file_bytes = f.read()
    boundary = "----CNKIBoundary" + uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="access_token"\r\n\r\n'
        f"{token}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{fn}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = head + file_bytes + tail

    parsed = urllib.parse.urlparse(url)
    last_err = None
    for attempt in range(1, max_retries + 1):
        conn = None
        try:
            print(f"[sync] 第 {attempt}/{max_retries} 次尝试：连接 Gitee ...", flush=True)
            conn = http.client.HTTPSConnection(
                parsed.hostname, parsed.port or 443, timeout=600)
            conn.connect()
            print(f"[sync] 已连接，构建 HTTP 请求头 ...", flush=True)
            conn.putrequest("POST", parsed.path + ("?" + parsed.query if parsed.query else ""))
            conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
            conn.putheader("Content-Length", str(len(body)))
            conn.putheader("User-Agent", "CNKI-Sync")
            conn.endheaders()
            print(f"[sync] 请求头已发送，开始流式上传 {fsize//1024//1024}MB ...", flush=True)
            # 分块发送，避免慢链路上单次 sendall 触发 socket 超时
            chunk = 1 << 20  # 1MB
            t0 = time.time()
            total_chunks = (len(body) + chunk - 1) // chunk
            for idx, i in enumerate(range(0, len(body), chunk), 1):
                conn.send(body[i:i + chunk])
                if idx % 5 == 0 or idx == total_chunks:  # 每 5 块或最后一块打一次日志
                    pct = min(100, round(i * 100 / len(body), 1))
                    elapsed = round(time.time() - t0, 1)
                    sent_mb = i // (1024 * 1024)
                    speed = round(sent_mb / elapsed, 1) if elapsed > 0 else 0
                    print(f"[sync] 上传进度: {pct}% ({sent_mb}/{fsize//1024//1024}MB) "
                          f"耗时 {elapsed}s  速度 ~{speed}MB/s", flush=True)
            print(f"[sync] 数据全部发送完毕，等待服务器响应 ...", flush=True)
            resp = conn.getresponse()
            result = json.loads(resp.read().decode("utf-8"))
            print(f"[sync] 上传成功！服务器返回: {result.get('name', '?')}", flush=True)
            return result
        except Exception as e:
            last_err = e
            print(f"[sync] 上传第 {attempt}/{max_retries} 次失败: {e}", flush=True)
        finally:
            if conn:
                conn.close()
        if attempt < max_retries:
            time.sleep(5 * attempt)  # 5s, 10s 退避
    raise RuntimeError(f"上传 exe 失败（已重试 {max_retries} 次）: {last_err}")


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
    notes = os.environ.get("NOTES", "")
    branch = os.environ.get("BRANCH", "main")

    # 收集待上传的 exe：EXE_PATH（单文件）优先；其次 EXE_PATH_RS；其余兼容键可选。
    exe_paths = []
    single = os.environ.get("EXE_PATH", "").strip()
    if single:
        exe_paths.append(single)
    for env_key in ("EXE_PATH_RS", "EXE_PATH_PYTHON", "EXE_PATH_RUST"):
        p = os.environ.get(env_key, "").strip()
        if p:
            exe_paths.append(p)

    missing = [n for n, v in (("GITEE_OWNER", owner), ("GITEE_REPO", repo),
                              ("GITEE_TOKEN", token), ("VERSION", version)) if not v]
    if not exe_paths:
        missing.append("EXE_PATH 或 EXE_PATH_RS")
    if missing:
        raise SystemExit("缺少环境变量: " + ", ".join(missing))
    for p in exe_paths:
        if not os.path.exists(p):
            raise SystemExit(f"未找到 exe: {p}")

    print(f"[sync] v{version}  owner={owner} repo={repo}", flush=True)
    print(f"[sync] 待上传 {len(exe_paths)} 个文件:", flush=True)
    for p in exe_paths:
        print(f"  - {p} ({os.path.getsize(p)//1024//1024}MB)", flush=True)

    print(f"[sync] 步骤 1/2: 创建/复用 Gitee Release ...", flush=True)
    rid = create_release(owner, repo, token, version, notes, branch)
    print(f"[sync] Release id={rid}", flush=True)
    print(f"[sync] 步骤 2/2: 上传 exe 附件 ...", flush=True)
    for p in exe_paths:
        upload_asset(owner, repo, token, rid, p)
    print(f"[sync] ✅ 全部完成：{len(exe_paths)} 个附件已同步到 Gitee Releases v{version}", flush=True)


if __name__ == "__main__":
    main()
