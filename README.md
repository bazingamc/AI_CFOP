# AI_CFOP - 魔方CFOP还原分析工具

通过AI分析你的魔方CFOP还原过程，提供技术评估和训练建议。

## 功能特点

- 自动识别CFOP各阶段（Cross / F2L / OLL / PLL）
- 计算各阶段观察时间和执行时间
- 定位卡顿点，分析TPS稳定性
- 支持单组/多组分析（多组可计算平均、波动度等统计指标）
- 生成针对性训练建议与提升路线
- 还原步骤时间轴可视化

## 快速开始

### 方式一：下载Release版本（推荐）

1. 前往 [Releases](../../releases) 页面下载最新版压缩包
2. 解压到任意目录
3. 双击 `AI_CFOP.exe` 运行

> 无需安装Python或任何依赖，开箱即用。

### 方式二：从源码运行

环境要求：Python 3.8+，依赖 `openai`

```bash
pip install openai
python cfop_analyzer_gui.py
```

### 使用步骤

📹 视频教程：[AI CFOP Analyzer——你的AI魔方老师](https://www.bilibili.com/video/BV1RtRtBuEBu/)

1. 在 [cstimer](https://www.cstimer.net/) 中连接智能魔方，打乱并还原
2. 点击成绩列表中的还原时间，完整复制弹窗中的**打乱公式**和**回顾**中的内容到软件输入框
3. 选择底色（程序会在不改变底色/顶色的4个前色中自动匹配最合适的观察坐标）
4. 配置API Key并选择模型
5. 点击「AI分析」开始分析
6. 分析结果可保存到本地

## API Key 获取

> 🌟 **使用邀请注册可获得价值16元的免费token！**

- 平台：[硅基流动 SiliconFlow](https://cloud.siliconflow.cn/i/k2AMkh34)
- **邀请码：`k2AMkh34`**
- 注册链接：https://cloud.siliconflow.cn/i/k2AMkh34
- 完成实名认证后即可获得token
- 使用 GLM5.1 可分析约 **180次**，使用 DeepSeek-v3.2 可分析约 **2000次**

## 模型选择

- 点击「刷新」按钮获取可用模型列表
- 不同模型分析结果差异较大，性能越高的模型分析越准确
- 高性能推荐：**GLM系列**
- 性价比推荐：**DeepSeek系列**

## 须知

- 本软件需配合智能魔方使用，不限品牌，连接cstimer进行还原即可
- 目前支持三阶魔方、任意底色、CFOP方法还原
- 本软件免费使用，用户自备API token

## 免责声明

本软件提供的魔方还原分析与训练建议基于算法模型生成，仅供参考，不构成任何专业指导或结果保证。用户应自行判断分析结果的适用性，并对使用本软件产生的任何后果承担责任。软件开发者不对因使用本软件导致的直接或间接损失负责。

## 打包为EXE

```bash
pip install pyinstaller
python build_exe.py
```

## 交流

QQ群：322267527
