# CNKI 论文引文获取工具

[![Build status](https://github.com/sulele89757/cnki-citation/actions/workflows/build.yml/badge.svg)](https://github.com/sulele89757/cnki-citation/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/sulele89757/cnki-citation)](https://github.com/sulele89757/cnki-citation/releases)

按论文标题在 **中国知网（CNKI）** 搜索论文，一键获取 **GB/T 7714-2025** 格式引文。支持单篇与 Excel 批量，自带拟人化反爬策略，可打包为单文件 exe。

> **软件名称统一为 `CNKI`**：安装目录、桌面快捷方式、开始菜单项均命名为 `CNKI`；窗口标题仍为中文「CNKI 引文工具」。源文件保留 `-py` / `-rs` 后缀（如 `cnki_citation.py`、`cnki-citation-rs`），便于区分语言与版本。

## 功能特性

- **单篇获取**：输入标题 → 自动搜索 → 界面内联显示引文 + 一键复制
- **批量获取（Excel）**：选 Excel → 逐条搜索 → 引文实时回填
  - 断点续传：已填行自动跳过，中断重跑不重复
  - 实时保存：每条成功后立即写入，崩溃不丢数据
  - 间隔控制：随机间隔 + 偶发长停顿，规避速率校验
  - 内置「下载 Excel 模板」按钮（基于 `批量引文模板.xlsx`）
- **拟人化反爬**：系统真实 Chrome + 持久化 Profile + playwright-stealth + 贝塞尔鼠标轨迹 / 逐字输入 / 随机滚动
- **系统托盘**：点「X」最小化到状态栏（知网风格「知」图标，白/深灰底 + 橙色外框 + 手写「知」），不退出；右键托盘菜单恢复 / 退出
- **自更新**：检测到新版本后一键下载并自动替换重启（私有仓库通过 Gitee API 签名下载）
- **单例模式**：禁止同时运行多个实例
- **清理历史**：设置页一键清理历史输出（引文 txt/json 与调试截图），不含浏览器 Profile，可释放多次运行累积的文件
- **图形界面（v4）**：CustomTkinter，左侧导航 + 三视图（单篇 / 批量 / 设置）+ 底栏（进度 + 日志），亮/暗主题自动适配

## 两个版本

仓库内含 Python 与 Rust 两种实现，**功能一致**；但 **Python 版仅作为参考代码保留，不再参与 CI 构建与发布**，实际可下载使用的只有 Rust 版安装包。

| | Python 版（参考代码） | Rust 版（推荐 · 实际发布） |
|---|---|---|
| 可执行文件 | `python/cnki_gui.py`（源码，需自装依赖运行） | `CNKI_<版本>_x64-setup.exe`（NSIS 安装包，默认命名） |
| 体积 | 取决于运行环境 | 安装包 ~6.6MB（安装时联网拉取 WebView2） |
| 技术栈 | CustomTkinter + Playwright(headless) | Tauri v2（WebView2）+ headless_chrome |
| 构建方式 | PyInstaller `--onefile`（已停用） | `cargo tauri build`（CI 自动） |
| 适用场景 | 阅读 / 改造 Python 逻辑 | 体积小、启动快、原生桌面体验 |

仅 Rust 版发布到 [Gitee 发行版](https://gitee.com/sulele/cnki-citation/releases)。

> **不再提供内置 WebView2 的离线安装包**（原 255MB 版）。改为安装包内置引导器、安装时自动下载 WebView2（详见下方「WebView2 运行环境」），安装包体积降至 ~6.6MB，也更利于 Gitee 分发。

## 环境要求

- Windows 10/11
- **WebView2 Runtime**：绝大多数系统已自带；安装包会在安装时自动联网下载安装（见下方链接，亦可提前手动预装）
- Google Chrome 或 Microsoft Edge（推荐 Chrome，指纹最真实）；两者都未安装时，工具会自动下载 Chromium 内核兜底（约 200MB，仅首次）
- Python 3.12+（仅 Python 版 GUI 需要系统 Python 自带 `tkinter`）

## 快速开始（exe 版）

1. 从 [Gitee 发行版](https://gitee.com/sulele/cnki-citation/releases) 下载 `CNKI_<版本>_x64-setup.exe`（Rust 版安装包，~6.6MB；文件名按 NSIS 默认规则随版本变化）。
2. 双击该安装包，桌面与开始菜单会生成 **`CNKI`** 快捷方式（安装目录为 `%LOCALAPPDATA%\CNKI`）。
3. 首次运行若提示缺少 WebView2，按提示联网安装即可（或预先装好，见下方链接）。
4. 单篇：输入标题 →「获取引文」；批量：选 Excel →「开始批量处理」。

数据目录：`C:\Users\<用户名>\.cnki_citation\`（跨运行持久化）

> Python 版未发布 exe，如需体验请见下方「从源码运行（Python 版 · 参考）」。

## WebView2 运行环境

Rust 安装包采用 `embedBootstrapper` 模式：**安装过程中自动从微软 CDN 下载并安装 WebView2 Runtime**，因此安装包本身仅 ~6.6MB，无需内置 255MB 运行时。

若目标机网络受限、或希望提前预装，可手动下载官方 WebView2 Runtime：

- 官方下载页：<https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/>
- 独立安装包（Evergreen Standalone，可离线安装）：<https://go.microsoft.com/fwlink/p/?LinkId=2124701>
- 引导器（小体积，安装时联网）：<https://go.microsoft.com/fwlink/p/?LinkId=2124703>

> 绝大多数 Win10/11 已自带 WebView2，双击安装包即可直接使用，无需手动处理。

## 从源码运行

### Python 版（仅参考，不构建发布）

```bash
cd python
python -m venv ../venv
../venv/Scripts/activate
pip install -r requirements.txt

python cnki_gui.py          # 启动 GUI
python cnki_citation.py "标题"   # 命令行单篇
python cnki_citation.py --excel papers.xlsx  # 命令行批量
```

> Python 版依赖系统浏览器与 `tkinter`，仅用于阅读与改造逻辑；正式分发一律使用下方 Rust 版。

### Rust / Tauri 版（从源码构建）

```bash
# 需要 Rust 稳定版 + 系统 Chrome/Edge（headless_chrome 驱动真实浏览器）
cd rust/src-tauri
cargo tauri build
# 产物：target/release/bundle/nsis/CNKI_<版本>_x64-setup.exe（NSIS 默认命名）
# bash rust/build_both.sh 会自动复制到 rust/dist/ 下同名文件
```

> 前端通过 `include_bytes!` 内嵌于二进制，无需单独资源目录；`tauri.conf.json` 中
> `productName` 已设为 `CNKI`，故安装目录与快捷方式均为 `CNKI`；`webviewInstallMode`
> 为 `embedBootstrapper`（安装时联网拉取 WebView2）。版本号由 CI 在构建时统一注入。

## Excel 批量格式

| 序号 | 标题 | 引文 |
|------|------|------|
| 1 | 新形势下企业财务管理信息化建设的途径探索 | （自动回填） |

- 标题列默认 `标题`，引文列默认 `引文`（不存在时自动新建）
- 列可用中文名、字母（`B`）或数字（`2`）指定：`--title-col B --out-col C`
- 间隔控制：`--min-gap 5 --max-gap 12`（单位秒，建议 ≥5）

## 版本更新检测

启动后 2 秒自动静默检测，顶部也有「检查更新」按钮。

- **私有仓库**：内嵌 Gitee 令牌（`cnki_citation.py` 的 `GITEE_TOKEN`），通过 API 签名下载附件（`foruda.gitee.com` 限时链接），无需公开仓库
- **自更新流程**：检测到新版本 → 弹窗确认 → 下载到 `%TEMP%` → 写 bat 替换 exe → 自动重启
- **⚠️ 安全提示**：当前内嵌的是写令牌（可反编译提取），生产环境建议替换为只读 PAT

## CI/CD（GitHub Actions → Gitee）

**方式 A — 正式发布（构建 + 发 GitHub/Gitee Release）：**

```
git tag v1.x.x && git push github --tags
```

**方式 B — 仅构建验证（不发 Release）：** 在 GitHub 仓库 Actions 页对 `Build and Release` 点 **Run workflow**（取最新 main，只构建不上传）。

> ⚠️ 不要用旧失败 job 的 **Re-run**：它会锁定旧 commit SHA，跑的是修复前的配置。务必发起全新运行（上述 A 或 B）。

触发 `.github/workflows/build.yml`，构建并发布：

1. **Rust 版**：`windows-latest` + `cargo tauri build`（embedBootstrapper）→ `CNKI_<版本>_x64-setup.exe`（NSIS 默认命名）
2. 发布到 **GitHub Release**
3. `sync_gitee.py` 同步到 **Gitee Releases**（国内下载源）

> Python 版不再参与 CI 构建（仅保留源码作为参考），因此 Gitee 上只会看到 Rust 安装包（`CNKI_<版本>_x64-setup.exe`）一个附件。

Gitee 令牌通过 GitHub Secret `GITEE_TOKEN` 注入。

## 本地构建

```bash
# Rust 版（仅构建，不上传）：bash rust/build_both.sh
# 产物：rust/dist/CNKI_<版本>_x64-setup.exe（embedBootstrapper，~6.6MB）
```

> `build_release.py`（原 Python 版本地构建脚本）已删除；Python 版保留源码在 `python/`，如需自跑见上方「从源码运行 → Python 版（仅参考）」。

> **关于软件名 / 目录 / exe 文件名**
> 软件名称统一为 **`CNKI`**（纯 ASCII，GitHub Actions 的 Windows runner 不会剥离字符）。
> 源文件保留 `-py` / `-rs` 后缀以区分语言与版本：Python 源码置于 `python/`（含 `cnki_citation.py` / `cnki_gui.py`），
> Rust crate 名 `cnki-citation-rs`（置于 `rust/`）。Rust 安装包以 `productName = "CNKI"` 构建并**沿用 NSIS 默认命名**
> `CNKI_<版本>_x64-setup.exe`（不再自定义 `-rs-installer` 之类名字；Python 已不发布，无需区分后缀），
> 安装目录与桌面 / 开始菜单快捷方式均为 `CNKI`；窗口标题仍为中文「CNKI 引文工具」。
> Python 版打包（仅参考）资源统一在 `python/assets/` 子目录，`--add-data` 的源路径与目标目录都必须是
> `assets/批量引文模板.xlsx;assets` 这种带 `assets/` 前缀的写法（运行时从 `sys._MEIPASS/assets` 读取）。

## 目录结构

```
cnki_search/
├── python/                   # Python 版（参考代码，不构建发布）
│   ├── cnki_citation.py      # 核心：搜索、反爬、引文提取、更新检测
│   ├── cnki_gui.py           # GUI（v4 左导航三视图 + 托盘 + 自更新）
│   ├── clear_icon_cache.bat  # 一键清理 Windows 图标缓存
│   ├── CNKICitationTool.spec # PyInstaller 规格（参考）
│   ├── requirements.txt      # 依赖清单
│   └── assets/               # 静态资源（图标 + 模板），所有资源统一放此目录
│       ├── app.ico           # 程序/任务栏窗口图标（9 帧多尺寸）
│       ├── generate_icons.py # 图标生成器：按尺寸分级绘制，避免小帧下采样发糊
│       ├── cnki_icon.png/.svg    # 亮色主题图标（白底 + 橙色外框 + 黑色手写「知」）
│       ├── cnki_icon_dark.png/.svg  # 深色主题图标（深灰底 + 橙色外框 + 白色手写「知」）
│       ├── cnki_icon.ico / cnki_icon_dark.ico  # 多分辨率 ICO（16~256）
│       └── 批量引文模板.xlsx  # 批量模式 Excel 模板
├── rust/                     # Rust / Tauri 原生版（cnki-citation-rs，实际发布）
│   ├── Cargo.toml            # 核心库 cnki_citation_rs（抓取引擎）
│   ├── build_both.sh         # 本地一键构建 embedBootstrapper 安装包
│   ├── src/                  # 库源码：behavior/citation/excel/stealth/update/version…
│   ├── dist/CNKI_<版本>_x64-setup.exe  # 本地构建产物（NSIS 默认命名，~6.6MB）
│   └── src-tauri/            # Tauri 应用（依赖上方库 + browser feature）
│       ├── Cargo.toml
│       ├── tauri.conf.json   # productName=CNKI，webviewInstallMode=embedBootstrapper
│       ├── src/              # commands.rs / main.rs（WebView 启动 + 命令注册）
│       ├── frontend/         # 内嵌前端（HTML/JS/CSS，编译时 include_bytes! 打入 exe）
│       └── icons/            # icon.ico（嵌 exe）+ icon.png
├── .github/workflows/
│   ├── build.yml             # GitHub Actions CI/CD（仅 Rust 安装包构建与发布）
│   └── sync_gitee.py         # 同步 Release 到 Gitee
├── venv/                     # 本地 Python 虚拟环境（git 忽略）
└── README.md
```

## 常见问题

**首次需要验证码？** 正常。手动过一次后 Profile 复用登录态，后续自动通过。

**点 X 程序退了？** 设计行为：X 最小化到托盘。彻底退出用托盘右键「退出」。

**安装提示缺少 WebView2？** 联网状态下安装包会自动下载安装；若网络受限，请先按「WebView2 运行环境」手动预装独立安装包。

**更新失败 403？** 旧版（v1.0.0~v1.0.3）内置的下载链接不支持私有仓库。手动下载 v1.0.4+ 覆盖即可。

**搜索不到论文？** 确认标题准确；最新论文可能尚未被 CNKI 收录。

## 隐私说明

- 浏览器 Profile（Cookie / 登录态 / 指纹）：`C:\Users\<用户名>\.cnki_citation\.chrome_profile\`，**不随 exe 分发**
- 输出文件：同目录下 `output/`
- Gitee 令牌：内嵌于 `cnki_citation.py`，仅用于更新检测与下载（详见上方安全提示）
