# MGTWR Tools

一个面向空间计量分析场景的桌面工具，提供数据准备、国家数据爬取、MGTWR 模型分析、结果可视化、显著性分析和若干独立处理工具。

## 主要功能

- 数据生成：按省份和年份整理基础数据
- 国家数据爬取：抓取统计数据并写入 Excel
- 模型分析：运行 GWR / GTWR / MGWR / MGTWR 相关分析流程
- 数据可视化：查看系数、尺度、空间分布和时间趋势
- 显著性分析：基于 t 值快速判断显著区域和时间点
- VIF 因子检验：快速检查自变量共线性
- 系数转 Shapefile：将结果表导出为空间点要素
- 数据标准化：支持常见标准化方法
- 应用信息：查看当前版本、远端版本并检查更新

## 运行环境

- Windows
- Python 3.11

## 安装依赖

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 启动方式

```powershell
python main.py
```

如果你使用项目内虚拟环境：

```powershell
.\.venv\Scripts\python.exe main.py
```

## 基本使用

### 1. 数据准备

进入“数据生成”或“国家数据爬取”页面，先准备好分析输入数据。

### 2. 模型分析

进入“模型分析”页面，选择输入文件、参数和输出位置，然后启动任务。

### 3. 结果查看

分析完成后，可以使用：

- “数据可视化”查看空间和时间图表
- “显著性分析”查看 t 值对应的显著性结果

### 4. 其他工具

“其他功能”里提供 VIF、Shapefile 导出和标准化等独立工具。

### 5. 检查更新

“应用信息”页面会显示：

- 当前本地版本
- 远端仓库最新发布版本
- 是否有可用更新

如果检测到新版本，可以直接打开对应的 GitHub release 页面。

## 版本管理

项目版本号保存在根目录 `version` 文件中。  
本地打包和 GitHub Actions 都读取这个文件。

## 本地打包

```powershell
cmd /d /c build.bat
```

默认输出：

```text
out/main.exe
```

## 项目结构

```text
app/
├── bootstrap/       # 应用组装
├── core/            # 配置、异常、资源路径
├── presentation/    # PyQt 页面、控件、presenter、图表渲染
├── application/     # 应用服务和 DTO
├── domain/          # 领域模型与规则
└── infrastructure/  # 文件读写、任务、外部请求
```

## 说明

- 仓库地址：`https://github.com/avengers-teams/mgtwr-tools`
- 更新检查依赖访问 GitHub API；如果网络受限，页面会提示检查失败
