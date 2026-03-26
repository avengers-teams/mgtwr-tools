# 开发说明

## 项目现状

当前运行主路径已经统一到 `app/`。  
后续开发只在新目录结构下进行，不再回到历史目录。

启动链路：

`main.py` -> `app/bootstrap/app_factory.py` -> `app/bootstrap/container.py` -> `app/presentation/views/main_window.py`

## 目录职责

```text
cdata/
├── main.py
├── build.bat
├── requirements.txt
├── version
├── assets/
└── app/
    ├── bootstrap/
    ├── core/
    ├── presentation/
    ├── application/
    ├── domain/
    └── infrastructure/
```

### `main.py`

应用入口。只负责启动，不放业务逻辑。

### `assets/`

静态资源目录。

- `icons/`：图标和图片
- `styles/`：QSS 样式
- `templates/`：模板文件

资源路径统一通过 `app.core.config` 读取，不要在代码里写死路径。

### `app/bootstrap/`

应用装配层。

- 创建容器
- 组装页面、服务、仓储
- 管理启动入口

这里只做装配，不写业务。

### `app/core/`

全局基础能力。

- 配置
- 异常
- 资源路径
- 版本和仓库地址

### `app/presentation/`

表现层，PyQt 相关代码都放这里。

- `views/`：窗口、页面、自定义控件
- `presenters/`：交互编排
- `viewmodels/`：页面状态
- `renderers/`：Matplotlib 图表渲染

规则：

- 页面负责展示和交互
- 不在页面里直接写复杂业务
- 不在页面里直接做文件读取和数据推断

### `app/application/`

应用服务层。

- 组织完整用例
- 调用仓储
- 调用领域规则
- 返回 DTO 或结果对象给表现层

规则：

- 可以依赖 `domain` 和 `infrastructure`
- 不依赖具体 PyQt 控件

### `app/domain/`

领域层。

- 核心数据模型
- 规则判断
- 版本比较、列名推断、显著性判定等纯逻辑

规则：

- 不依赖 PyQt
- 不处理具体界面和文件 I/O

### `app/infrastructure/`

基础设施层。

- Excel 读写
- GitHub release 请求
- 后台任务实现
- 第三方库接入细节

## 依赖方向

推荐方向：

`presentation -> application -> domain`  
`application -> infrastructure`  
`bootstrap -> 组装全部层`

避免：

- `domain -> presentation`
- `application -> QWidget`
- `views -> 直接读写 Excel`

## 常见开发动作

### 新增页面

1. 在 `app/presentation/views/pages/` 新建页面
2. 有复杂交互时，在 `app/presentation/presenters/` 新建 presenter
3. 需要状态对象时，在 `app/presentation/viewmodels/` 新建 viewmodel
4. 在 `app/bootstrap/container.py` 注入依赖
5. 在 `app/presentation/views/main_window.py` 注册导航

### 新增服务

放到 `app/application/services/`。  
如果涉及外部系统或文件读写，具体实现放到 `app/infrastructure/`。

### 新增图表

- 渲染代码放 `app/presentation/renderers/`
- 输入对象放 `app/application/dto/`
- 规则判断放 `app/domain/`

### 新增配置

统一放到 `app/core/config.py`。  
版本号统一读取根目录 `version` 文件。

## 运行与打包

本地运行：

```powershell
.\.venv\Scripts\python.exe main.py
```

本地打包：

```powershell
cmd /d /c build.bat
```

GitHub Actions 也会读取根目录 `version` 作为打包版本。
