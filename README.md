# AI\_CFOP - 集练习、复盘、统计、AI分析、于一体的智能魔方训练工具

<p align="center">
  <strong>内嵌 csTimer 计时器 · AI 深度分析还原过程 · 精准定位瓶颈 · 专业训练建议</strong>
</p>

***

## 项目简介

AI\_CFOP 是一款面向三阶魔方 CFOP 选手的一体化智能训练工具。软件内嵌 csTimer 计时器，连接蓝牙智能魔方即可直接在软件内练习，还原数据一键同步，无需手动导入。自动拆解 CFOP 七个阶段（Cross → F2L×4 → OLL → PLL），计算各阶段的 TPS、观察时间、卡顿点和废步，并提供专业级技术评估与训练指导。

## 核心功能

### 内嵌 csTimer · 练习一体化

- **内嵌 csTimer 计时器** — 软件内直接打开 csTimer，连接蓝牙智能魔方即可练习
- **一键同步数据** — 还原完成后点击「同步csTimer数据」，自动导入所有还原记录
- **无需手动导入** — 告别在 csTimer 网站还原再导出数据的繁琐流程

### 深度分析 · AI 复盘

- **自动底色识别** — 无需手动选择底色，完美适配6色底选手
- **CFOP 七阶段拆解** — Cross / F2L-1\~4 / OLL / PLL 完整拆分
- **转体识别** — 无需陀螺仪也能自动识别 y/y'/y2 转体，还原真实观察视角
- **OLL/PLL Case 识别** — 自动识别还原中遇到的 OLL（57 种）和 PLL（21 种）编号
- **单组/多组分析** — 单组深度剖析，多组横向对比
- **Ao12 分析** — 最佳/最差 Ao12 深度 AI 分析
- **时间轴可视化** — 还原步骤时间轴，直观展示各阶段用时分布
- **流式 AI 输出** — 分析结果实时流式显示，支持中途停止

### 智能训练

- **OLL/PLL 公式库** — 57 个 OLL + 21 个 PLL，每个 Case 含多个备选公式与状态图
- **训练统计分析** — 各 Case 出现次数、平均步数/用时/TPS/观察时间，并按优先级给出需要重点训练的Case
- **训练总结报告** — 含折线图/直方图/Ao12 趋势，支持 PDF 导出
- **AI 训练建议** — 基于训练数据生成针对性提升路线

### 数据管理

- **csTimer 无缝集成** — 内嵌 csTimer 网页，支持一键同步数据
- **智能粘贴** — 监听剪贴板，自动识别 csTimer 弹窗数据
- **多格式导入导出** — 支持 csTimer JSON、CSV 导入/导出
- **多用户管理** — 支持创建/切换/删除用户，独立数据隔离
- **本地 SQLite 存储** — 所有数据本地保存，隐私安全

### 统计面板

- PB / 平均用时 / 平均 TPS / 各阶段统计卡片
- 优缺点标签（12 项优点 + 12 项缺点自动评定）
- 历史趋势图

## 快速开始

### 方式一：下载 Release 版本（推荐）

1. 前往 [Releases](../../releases) 页面下载最新版
2. 安装软件到任意目录，双击 `AI_CFOP.exe` 运行

> 无需安装 Python 或任何依赖，开箱即用。（win7和老版本win10需单独安装WebView2 Runtime）

### 方式二：从源码运行

```bash
# 最低依赖
pip install openai

# 完整功能（推荐）
pip install openai tkwebview matplotlib reportlab Pillow

# 启动
python cfop_analyzer_gui.py
```

> 环境要求：Python 3.8+

## 使用流程

1. 在 [csTimer](https://www.cstimer.net/) 标签页中连接智能魔方，开始练习
2. 在数据管理页面，点击“同步csTimer数据”
3. 在设置页面配置 API Key 并选择模型
4. 在数据管理页面，选中一个或多个还原数据，点击”分析选中项“，会自动跳转到深度分析页面
5. 点击「AI 分析」，获取专业评估与训练建议

## API Key 获取

> 使用邀请注册可获得价值 16 元的免费 token！

- 平台：[硅基流动 SiliconFlow](https://cloud.siliconflow.cn/i/k2AMkh34)
- 邀请码：`k2AMkh34`
- 完成实名认证后即可使用
- 使用 GLM-5.1 可分析约 **180 次**，使用 DeepSeek-v3.2 可分析约 **2000 次**

## 模型选择

| 推荐级别 | 模型系列        | 特点            |
| ---- | ----------- | ------------- |
| 高性能  | GLM 系列      | 分析更精准，适合追求细节  |
| 性价比  | DeepSeek 系列 | 分析次数更多，适合日常训练 |

> 点击「刷新」按钮可获取当前可用模型列表。

## 项目结构

```
AI_Cube_Open/
├── cfop_analyzer_gui.py   # 程序入口
├── gui.py                 # GUI 主类（7 个标签页）
├── analyzer.py            # CFOP 还原分析引擎
├── cube.py                # 三阶魔方 Cubie Model
├── move_utils.py          # 步骤解析与朝向映射
├── config.py              # 配置参数、OLL/PLL 公式库
├── prompts.py             # AI 提示词模板
├── api_utils.py           # API 调用与配置工具
├── memory_db.py           # SQLite 数据库管理
├── daily_report.py        # 训练总结报告（图表/PDF）
├── user_manager.py        # 多用户管理
├── markdown_renderer.py   # Markdown 渲染器
├── build_exe.py           # PyInstaller 打包脚本
├── installer.iss          # Inno Setup 安装脚本
└── png/
    ├── OLL/               # OLL 1-57 状态图
    └── PLL/               # PLL 21 个 Case 状态图
```

## 打包为 EXE

```bash
pip install pyinstaller

# 仅打包 EXE
python build_exe.py

# 打包 EXE + 构建安装包
python build_exe.py --installer
```

## 技术栈

| 类别    | 技术                          |
| ----- | --------------------------- |
| 语言    | Python 3.8+                 |
| GUI   | tkinter + ttk               |
| 内嵌浏览器 | tkwebview (WebView2)        |
| AI    | OpenAI 兼容 API (SiliconFlow) |
| 数据库   | SQLite3                     |
| 图表    | matplotlib                  |
| PDF   | reportlab                   |
| 图片    | Pillow                      |

## 须知

- 本软件需配合智能魔方使用，不限品牌，通过内嵌 csTimer 连接即可
- 目前支持三阶魔方、任意底色、CFOP 方法还原
- 本软件免费使用，用户自备 API token

## 免责声明

本软件提供的魔方还原分析与训练建议基于算法模型生成，仅供参考，不构成任何专业指导或结果保证。用户应自行判断分析结果的适用性，并对使用本软件产生的任何后果承担责任。软件开发者不对因使用本软件导致的直接或间接损失负责。

## 交流

QQ 群：322267527

## 开源许可

本项目基于 [GNU General Public License v3.0](LICENSE) 开源。
