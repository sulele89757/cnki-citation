# CNKI 论文引文获取工具

按论文标题在 **中国知网（CNKI）** 搜索论文，一键获取 **GB/T 7714-2025** 格式引文。支持单篇与 Excel 批量，自带拟人化反爬策略，可打包为单文件 exe，支持系统托盘与 Gitee 版本更新检测。

## 功能特性

- **单篇获取**：输入标题，自动搜索并提取「GB/T 7714-2025 格式引文」
- **批量获取（Excel）**：解析 Excel → 逐条搜索 → 引文实时回填引文列
  - 断点续传：已填行自动跳过，中断后重跑不重复
  - 实时保存：每条成功后立即写入，进程崩溃不丢数据
  - 间隔控制：篇间随机间隔 + 偶发长停顿，规避 CNKI 兜底速率校验
- **拟人化反爬**：系统真实 Chrome + 持久化 Profile + playwright-stealth + 贝塞尔鼠标轨迹/逐字输入/随机滚动，规避机器人校验
- **系统托盘**：点「X」最小化到状态栏，不退出进程；双击托盘图标或菜单「显示窗口」恢复
- **版本更新检测**：启动时自动检测 Gitee 仓库最新 Release，有更新弹窗提示下载
- **图形界面**：CustomTkinter 暗色蓝主题，**界面跟随系统**（亮/暗自动适配）

## 环境要求

- Windows 10/11
- 已安装 **Google Chrome**（推荐，指纹最真实）；未安装时自动回退 Playwright 内置 Chromium
- Python 3.12+（GUI 依赖系统 Python 自带的 `tkinter`；本机使用系统 Python 3.12 创建 venv）

## 快速开始（exe 版，免安装）

1. 下载 `dist/CNKI引文工具.exe`
2. 双击运行（首次可能需手动通过一次验证码，之后复用 Profile 自动通过）
3. 单篇：输入标题 →「获取引文」；批量：选 Excel →「开始批量处理」

输出与浏览器 Profile 位于：
`C:\Users\<你的用户名>\.cnki_citation\`（跨运行持久化，不受 exe 临时目录影响）

## 从源码运行

```bash
# 1. 创建 venv（需系统 Python 3.12，自带 tkinter）
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. 单篇
python cnki_citation.py "论文标题"

# 3. Excel 批量
python cnki_citation.py --excel papers.xlsx

# 4. 启动 GUI
python cnki_gui.py
```

## Excel 批量格式

| 序号 | 标题 | 引文 |
|------|------|------|
| 1 | 新形势下企业财务管理信息化建设的途径探索 | （自动回填） |

- 标题列默认 `标题`，引文列默认 `引文`（不存在时自动新建）
- 列可用中文名、字母（`B`）或数字（`2`）指定：`--title-col B --out-col C`
- 间隔控制：`--min-gap 5 --max-gap 12`（单位秒，生产建议 ≥5）

## 版本更新检测（Gitee）

GUI 顶部有「检查更新」按钮，启动后 2 秒自动静默检测一次。

配置（`cnki_citation.py` 顶部）：

```python
APP_VERSION = "1.0.0"
GITEE_OWNER = "你的Gitee用户名"   # 改成真实值
GITEE_REPO  = "cnki-citation"     # 改成真实值
```

发布流程：

1. 把 `GITEE_OWNER`/`GITEE_REPO` 改为真实仓库（**仓库需公开**，否则未认证 API 无法访问）
2. 重新打包 exe（见下）
3. 在 Gitee 仓库「发行版」创建 Release，标签填 `v1.0.1`（高于 `APP_VERSION` 即触发更新提示）

> Gitee 的「代码片段 / Gist」只适合分享小段代码，不适合版本发布；更新检测统一用仓库 **Releases**。

## 打包为 exe

```bash
# 依赖已装在专用 gui venv
VENV_GUI="C:\Users\sule\.workbuddy\binaries\python\envs\gui"

# 注意：沙箱环境会拦截删除操作，需将 --workpath/--distpath 指到系统临时目录
TMPD="$LOCALAPPDATA/Temp/cnki_build"
TMPO="$LOCALAPPDATA/Temp/cnki_dist"
"$VENV_GUI/Scripts/pyinstaller.exe" \
  --name "CNKI引文工具" --onefile --windowed --icon app.ico \
  --workpath "$TMPD" --distpath "$TMPO" \
  --hidden-import customtkinter \
  --hidden-import playwright_stealth --hidden-import openpyxl --hidden-import pystray \
  --collect-all playwright --collect-all playwright_stealth --collect-all pystray \
  cnki_gui.py
mkdir -p dist && cp "$TMPO/CNKI引文工具.exe" dist/
```

产物：`dist/CNKI引文工具.exe`（单文件，双击即用）。

## 目录结构

```
cnki_search/
├── cnki_citation.py   # 核心：搜索、反爬、引文提取、Excel 批量、更新检测
├── cnki_gui.py        # CustomTkinter 图形界面 + 系统托盘
├── make_icon.py       # 生成 app.ico 图标
├── app.ico            # 程序图标
├── requirements.txt   # 依赖清单
├── README.md
├── test_papers.xlsx   # 测试用 Excel 样例
└── dist/              # 打包产物（exe）
```

## 常见问题

**首次运行需要验证码？**
正常。首次 Profile 为空，CNKI 可能要求验证码。手动完成一次后，后续运行自动复用登录态，不再出现。

**搜索不到论文？**
确认标题准确；最新发表的论文可能尚未被 CNKI 收录。

**点「X」关不掉 / 程序还在后台？**
这是设计行为——点「X」会最小化到系统托盘，进程继续运行（便于长任务进行中收起窗口）。彻底退出请用托盘菜单「退出」。

**引用按钮找不到 / 页面结构变了？**
检查 `output/` 下的调试截图；确保使用系统 Chrome 而非 Playwright 内置 Chromium。

## 隐私说明

浏览器 Profile（含 Cookie / 登录态 / 指纹）保存在 `C:\Users\<用户名>\.cnki_citation\.chrome_profile\`，**不随 exe 分发**，已在 `.gitignore` 中忽略。
