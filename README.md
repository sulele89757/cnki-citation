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
- **系统托盘**：点「X」最小化到状态栏（蓝底白「知」图标），不退出；右键托盘菜单恢复 / 退出
- **自更新**：检测到新版本后一键下载并自动替换重启（私有仓库通过 Gitee API 签名下载）
- **单例模式**：禁止同时运行多个实例
- **图形界面（v4）**：CustomTkinter，左侧导航 + 三视图（单篇 / 批量 / 设置）+ 底栏（进度 + 日志），亮/暗主题自动适配

## 环境要求

- Windows 10/11
- Google Chrome（推荐，指纹最真实）；未安装时回退 Playwright 内置 Chromium
- Python 3.12+（GUI 需系统 Python 自带 `tkinter`）

## 快速开始（exe 版）

1. 从 [Gitee 发行版](https://gitee.com/sulele/cnki-citation/releases) 下载 `CNKI引文工具.exe`
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

```
git tag v1.x.x && git push github main --tags
```

触发 `.github/workflows/build.yml`：

1. `windows-latest` + PyInstaller 构建 exe
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

产物：`dist/CNKI引文工具.exe`（~57MB 单文件）

## 目录结构

```
cnki_search/
├── cnki_citation.py          # 核心：搜索、反爬、引文提取、更新检测
├── cnki_gui.py               # GUI（v4 左导航三视图 + 托盘 + 自更新）
├── build_release.py          # 本地构建 + 发布脚本
├── clear_icon_cache.bat      # 一键清理 Windows 图标缓存
├── requirements.txt          # 依赖清单
├── assets/                   # 静态资源（图标 + 模板，打包进 exe）
│   ├── app.ico               # 程序/任务栏窗口图标（多尺寸）
│   ├── cnki_icon.png/.svg    # 亮色主题图标（蓝底「知」）
│   ├── cnki_icon_dark.png/.svg  # 暗色主题图标（橙色边框）
│   └── 批量引文模板.xlsx      # 批量模式 Excel 模板
├── .github/workflows/
│   ├── build.yml             # GitHub Actions CI/CD
│   └── sync_gitee.py         # 同步 Release 到 Gitee
├── README.md
└── dist/                     # 构建产物
    └── CNKI引文工具.exe
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
