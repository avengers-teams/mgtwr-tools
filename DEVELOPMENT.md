# 开发文档

## 目标

本项目已经将运行时主路径迁移到 `app/` 目录。

后续开发的基本原则只有两条：

1. 所有新增代码只放在 `app/` 下。
2. `main.py` 只能通过 `app/bootstrap` 组装应用，不能再直接从旧目录拼装界面或业务逻辑。

历史目录已经从运行主路径中移除。后续开发只能在 `app/` 下进行。

## 目录职责

```text
my_project/
├── main.py
├── requirements.txt
├── DEVELOPMENT.md
├── assets/
│   ├── icons/
│   ├── styles/
│   └── templates/
└── app/
    ├── bootstrap/
    ├── core/
    ├── presentation/
    ├── application/
    ├── domain/
    └── infrastructure/
```

### `main.py`

绝对入口点。

职责：

- 启动 Qt 应用
- 调用 `app.bootstrap.app_factory`
- 不承载业务逻辑

### `assets/`

静态资源目录。

职责：

- `icons/`：应用图标、图片资源
- `styles/`：QSS 样式
- `templates/`：Excel 模板、帮助页面等静态模板

约束：

- 资源路径统一通过 `app.core.config.resolve_resource_path()` 或 `app.core.urltools.get_resource_path()` 获取
- 不允许在代码里写死相对路径

## `app/` 总体分层

### `app/bootstrap/`

应用组装层。

职责：

- 创建容器
- 装配页面、服务、仓储、任务对象
- 提供应用入口工厂

当前文件：

- [app_factory.py](c:/Users/YZR/Desktop/cdata/app/bootstrap/app_factory.py)
- [container.py](c:/Users/YZR/Desktop/cdata/app/bootstrap/container.py)

规则：

- 可以依赖整个 `app/`
- 不写业务逻辑，只做装配

### `app/core/`

全局基础设施。

职责：

- 全局配置
- 全局异常
- 通用资源路径解析

当前文件：

- [config.py](c:/Users/YZR/Desktop/cdata/app/core/config.py)
- [exceptions.py](c:/Users/YZR/Desktop/cdata/app/core/exceptions.py)
- [urltools.py](c:/Users/YZR/Desktop/cdata/app/core/urltools.py)

规则：

- `core` 不依赖 `presentation`
- 只放跨层复用且稳定的基础能力

### `app/presentation/`

UI 展现层，PyQt 专属。

职责：

- `views/`：QWidget / QMainWindow / 自定义控件
- `presenters/`：页面交互编排
- `viewmodels/`：视图状态数据
- `renderers/`：Matplotlib 图表渲染

#### `app/presentation/views/`

职责：

- 页面布局
- 控件信号绑定
- 仅做 UI 展示与用户交互转发

当前主窗口：

- [main_window.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/main_window.py)

当前页面：

- [data_preparation.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/pages/data_preparation.py)
- [data_crawling.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/pages/data_crawling.py)
- [MGTWR_analysis.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/pages/MGTWR_analysis.py)
- [data_visualization.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/pages/data_visualization.py)
- [significance_analysis.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/pages/significance_analysis.py)
- [task_manager.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/pages/task_manager.py)
- [data_validation/index.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/pages/data_validation/index.py)

当前控件：

- [button.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/button.py)
- [combobox.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/combobox.py)
- [console.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/console.py)
- [fluent_surface.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/fluent_surface.py)
- [input.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/input.py)
- [list_widget.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/list_widget.py)
- [message_box.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/message_box.py)
- [parameter_box.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/widgets/parameter_box.py)

规则：

- 不直接读取 Excel 文件
- 不直接做复杂数据推断
- 不直接访问 `multiprocessing.Queue`
- 页面应该优先调用 presenter 或 service

#### `app/presentation/presenters/`

职责：

- 把用户动作翻译成用例调用
- 维护页面状态切换
- 减少页面类中的业务判断

当前文件：

- [significance_presenter.py](c:/Users/YZR/Desktop/cdata/app/presentation/presenters/significance_presenter.py)

规则：

- presenter 可以依赖 `application`
- presenter 不直接依赖 `infrastructure` 的具体细节，除非通过容器注入

#### `app/presentation/viewmodels/`

职责：

- 组织页面状态
- 让页面渲染依赖状态对象，而不是散乱字段

当前文件：

- [significance_viewmodel.py](c:/Users/YZR/Desktop/cdata/app/presentation/viewmodels/significance_viewmodel.py)

#### `app/presentation/renderers/`

职责：

- Matplotlib 图表构造
- 图形格式、坐标轴格式化、颜色、字体处理

当前文件：

- [model_visualization.py](c:/Users/YZR/Desktop/cdata/app/presentation/renderers/model_visualization.py)
- [significance_chart_factory.py](c:/Users/YZR/Desktop/cdata/app/presentation/renderers/significance_chart_factory.py)

规则：

- 只做渲染，不做文件 I/O
- 输入应为数据对象、DTO 或明确参数

### `app/application/`

应用服务层。

职责：

- 编排一次完整用例
- 调用仓储读取数据
- 调用领域规则和渲染器
- 返回 DTO / 结果对象给表现层

当前文件：

- [result_file_service.py](c:/Users/YZR/Desktop/cdata/app/application/services/result_file_service.py)
- [significance_service.py](c:/Users/YZR/Desktop/cdata/app/application/services/significance_service.py)
- [data_analysis.py](c:/Users/YZR/Desktop/cdata/app/application/services/data_analysis.py)
- [reptile.py](c:/Users/YZR/Desktop/cdata/app/application/services/reptile.py)
- [spatial_export.py](c:/Users/YZR/Desktop/cdata/app/application/services/spatial_export.py)
- [standardization.py](c:/Users/YZR/Desktop/cdata/app/application/services/standardization.py)
- [vif.py](c:/Users/YZR/Desktop/cdata/app/application/services/vif.py)
- [xlsx_tools.py](c:/Users/YZR/Desktop/cdata/app/application/services/xlsx_tools.py)

DTO：

- [significance.py](c:/Users/YZR/Desktop/cdata/app/application/dto/significance.py)

规则：

- 可以调用 `domain`、`infrastructure`、`presentation.renderers`
- 不应依赖 PyQt 控件对象

### `app/domain/`

领域核心层。

职责：

- 核心数据模型
- 与具体 UI 无关的规则与判断

当前文件：

- [result_dataset.py](c:/Users/YZR/Desktop/cdata/app/domain/models/result_dataset.py)
- [chart_spec.py](c:/Users/YZR/Desktop/cdata/app/domain/models/chart_spec.py)
- [column_inference.py](c:/Users/YZR/Desktop/cdata/app/domain/policies/column_inference.py)
- [significance_policy.py](c:/Users/YZR/Desktop/cdata/app/domain/policies/significance_policy.py)

规则：

- 领域层不依赖 PyQt
- 尽量不依赖具体文件路径和具体页面

### `app/infrastructure/`

基础设施层。

职责：

- Excel 读写实现
- 多进程、多线程、队列桥接
- 第三方库集成细节

当前文件：

- [dataframe_loader.py](c:/Users/YZR/Desktop/cdata/app/infrastructure/repositories/dataframe_loader.py)
- [excel_result_repository.py](c:/Users/YZR/Desktop/cdata/app/infrastructure/repositories/excel_result_repository.py)
- [analysis.py](c:/Users/YZR/Desktop/cdata/app/infrastructure/tasks/analysis.py)
- [crawling.py](c:/Users/YZR/Desktop/cdata/app/infrastructure/tasks/crawling.py)

规则：

- 可以依赖第三方库
- 不负责页面控件操作

## 层间依赖规则

推荐依赖方向：

```text
presentation -> application -> domain
presentation -> application -> infrastructure
bootstrap -> presentation/application/domain/infrastructure
infrastructure -> domain/core
```

禁止：

- `domain -> presentation`
- `domain -> PyQt`
- `application -> QWidget`
- `presentation/views -> 直接读写 Excel 文件`

## 当前运行主路径

启动路径：

1. [main.py](c:/Users/YZR/Desktop/cdata/main.py)
2. [app/bootstrap/app_factory.py](c:/Users/YZR/Desktop/cdata/app/bootstrap/app_factory.py)
3. [app/bootstrap/container.py](c:/Users/YZR/Desktop/cdata/app/bootstrap/container.py)
4. [app/presentation/views/main_window.py](c:/Users/YZR/Desktop/cdata/app/presentation/views/main_window.py)

这条链路已经不再依赖旧目录来完成运行时装配。

## 如何新增功能

### 新增一个页面

1. 在 `app/presentation/views/pages/` 新建页面文件
2. 如果页面存在复杂交互，在 `app/presentation/presenters/` 新建 presenter
3. 如果页面需要状态对象，在 `app/presentation/viewmodels/` 新建 viewmodel
4. 如果页面需要业务能力，在 `app/application/services/` 新建 service
5. 在 `app/presentation/views/main_window.py` 注册导航入口
6. 在 `app/bootstrap/container.py` 注入依赖

### 新增一个数据读取器

1. 放到 `app/infrastructure/repositories/`
2. 若存在跨页面复用的读取流程，在 `app/application/services/` 增加应用服务封装
3. 页面不要直接 new pandas 读取逻辑

### 新增一个图表

1. 图表渲染代码放 `app/presentation/renderers/`
2. 图表输入参数放 `app/application/dto/`
3. 图表规则判断放 `app/domain/policies/`
4. 页面通过 service 或 presenter 调用，不直接拼装复杂数据流程

### 新增一个后台任务

1. 任务执行体放 `app/infrastructure/tasks/`
2. 页面只负责启动、取消和展示状态
3. 进程/线程状态管理统一由任务管理页或后续的任务服务承接

## 后续建议

当前建议继续做两类工作：

1. 继续把重量级页面逻辑从 `app/presentation/views/pages/*.py` 下沉到 presenter / application service
2. 给 `domain` / `application` 补单元测试

优先顺序建议：

1. 重构 `data_visualization`
2. 重构 `MGTWR_analysis`
3. 统一任务调度与事件总线
4. 补测试
