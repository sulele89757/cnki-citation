# CNKI 论文引文获取工具

按论文标题在 **中国知网（CNKI）** 搜索论文，一键获取 **GB/T 7714-2025** 格式引文。支持单篇与 Excel 批量，自带拟人化反爬策略，可打包为单文件 exe。

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

## 环境要求

- Windows 10/11
- Google Chrome（推荐，指纹最真实）；未安装时回退 Playwright 内置 Chromium
- Python 3.12+（GUI 需系统 Python 自带 `tkinter`）

## 快速开始（exe 版）

1. 从 [Gitee 发行版](https://gitee.com/sulele/cnki-citation/releases) 下载 `CNKICitationTool.exe`
   （exe 文件名是英文，但软件窗口标题仍为「CNKI 引文工具」，原因见文末「关于 exe 文件名」）
2. 双击运行（首次可能需手动过一次验证码，之后 Profile 自动复用）
3. 单篇：输入标题 →「获取引文」；批量：选 Excel →「开始批量处理」

数据目录：`C:\Users\<用户名>\.cnki_citation\`（跨运行持久化）

## 从源码运行

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

python cnki_gui.py          # 启动 GUI
python cnki_citation.py "标题"   # 命令行单篇
python cnki_citation.py --excel papers.xlsx  # 命令行批量
```

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

触发 `.github/workflows/build.yml`：

1. `windows-latest` + PyInstaller 构建 exe（`rm -f` 清残留 spec 后构建，避免 re-run 沿用旧 datas 路径）
2. 发布到 **GitHub Release**
3. `sync_gitee.py` 同步到 **Gitee Releases**（国内下载源）

Gitee 令牌通过 GitHub Secret `GITEE_TOKEN` 注入。

## 本地构建

```bash
# 用 build_release.py（只构建，不上传）
python build_release.py --dry-run

# 构建并发布到 Gitee
python build_release.py
```

产物：`dist/CNKICitationTool.exe`（~57MB 单文件）

> **关于 exe 文件名**
> GitHub Actions 的 Windows runner 会剥掉文件名中的非 ASCII 字符：`--name` 若含中文，
> 构建出的 exe 会被压成 `CNKI.exe`。因此内部标识统一固定为英文
> `APP_NAME = "CNKICitationTool"`（`cnki_gui.py`），用于 exe 文件名、托盘图标名、
> 自更新临时文件名；中文仅保留在用户界面文案（窗口标题「CNKI 引文工具」、品牌标签、
> 提示语、托盘 tooltip），不影响任何功能。
> 打包时资源均在 `assets/` 子目录，`--add-data` 的源路径与目标目录都必须是
> `assets/批量引文模板.xlsx;assets` 这种带 `assets/` 前缀的写法（运行时从
> `sys._MEIPASS/assets` 读取）。

## 目录结构

```
cnki_search/
├── cnki_citation.py          # 核心：搜索、反爬、引文提取、更新检测
├── cnki_gui.py               # GUI（v4 左导航三视图 + 托盘 + 自更新）
├── clear_icon_cache.bat      # 一键清理 Windows 图标缓存
├── requirements.txt          # 依赖清单
├── assets/                   # 静态资源（图标 + 模板，打包进 exe），所有资源统一放此目录
│   ├── app.ico               # 程序/任务栏窗口图标（9 帧多尺寸）
│   ├── generate_icons.py     # 图标生成器：按尺寸分级绘制，避免小帧下采样发糊
│   ├── cnki_icon.png/.svg    # 亮色主题图标（白底 + 橙色外框 + 黑色手写「知」，不透明）
│   ├── cnki_icon_dark.png/.svg  # 深色主题图标（深灰底 + 橙色外框 + 白色手写「知」，不透明）
│   ├── cnki_icon.ico / cnki_icon_dark.ico  # 多分辨率 ICO（16~256，窗口/任务栏用，小帧去「知」加粗框）
│   └── 批量引文模板.xlsx      # 批量模式 Excel 模板
├── .github/workflows/
│   ├── build.yml             # GitHub Actions CI/CD
│   └── sync_gitee.py         # 同步 Release 到 Gitee
├── README.md
└── dist/                     # 构建产物
    └── CNKICitationTool.exe
```

## 常见问题

**首次需要验证码？** 正常。手动过一次后 Profile 复用登录态，后续自动通过。

**点 X 程序退了？** 设计行为：X 最小化到托盘。彻底退出用托盘右键「退出」。

**更新失败 403？** 旧版（v1.0.0~v1.0.3）内置的下载链接不支持私有仓库。手动下载 v1.0.4+ 覆盖即可。

**搜索不到论文？** 确认标题准确；最新论文可能尚未被 CNKI 收录。

## 隐私说明

- 浏览器 Profile（Cookie / 登录态 / 指纹）：`C:\Users\<用户名>\.cnki_citation\.chrome_profile\`，**不随 exe 分发**
- 输出文件：同目录下 `output/`
- Gitee 令牌：内嵌于 `cnki_citation.py`，仅用于更新检测与下载（详见上方安全提示）
