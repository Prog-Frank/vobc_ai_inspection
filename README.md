# VOBC 日志解析与智能巡检系统（vobc_ai_inspection）

基于 Python FastAPI 构建的 VOBC（车载控制器）日志解析与智能巡检系统，支持高效解析二进制日志文件、智能规则巡检、案例管理和数据可视化。

## 功能特性

### 📊 核心功能

| 功能模块 | 说明 |
|---------|------|
| **日志解析** | 支持 VOBC 二进制日志文件的高效解析，基于配置文件动态解析不同系统的数据帧 |
| **智能巡检** | 基于规则引擎的自动化巡检，支持多条件逻辑判断，自动识别异常数据 |
| **数据绘制** | 交互式数据可视化，支持曲线图、直方图、散点图，支持缩放和悬停交互 |
| **案例库** | 故障案例的存储与检索，支持字段匹配查询 |

### ✨ 技术亮点

- **内存映射**：使用 `mmap` 实现大文件零拷贝读取，支持 GB 级日志文件
- **按需解析**：支持分页解析，避免一次性加载全部数据
- **ECharts 可视化**：前端交互式图表，支持缩放、拖动、悬停提示
- **规则引擎**：灵活的巡检规则配置，支持 AND/OR 逻辑组合

## 项目结构

```
sz6_vobc_ai_inspection/
├── config/                    # 配置文件目录
│   └── data_configuration_file/  # 数据解析配置（各系统帧结构定义）
├── rules/                     # 规则文件目录
│   ├── inspection/            # 巡检规则（JSON格式）
│   └── 巡检规则编写说明.md      # 规则编写文档
├── src/                       # 核心源代码
│   ├── __init__.py
│   ├── parser.py              # 日志解析器
│   ├── plotter.py             # 数据绘图模块
│   └── utils.py               # 工具函数
├── ui_server/                 # Web UI 服务
│   ├── app.py                 # FastAPI 主程序
│   ├── run_web.py             # 启动脚本
│   └── templates/
│       └── index.html         # 前端页面
├── log_data/                  # 日志数据目录
│   └── uploaded/              # 上传的日志文件
├── cases.db                   # 案例库 SQLite 数据库
└── requirements.txt           # 依赖清单
```

## 快速开始

### 环境要求

- Python 3.10+
- 依赖库：见 `requirements.txt`

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

```bash
cd ui_server
python run_web.py
```

服务启动后访问：http://localhost:8000

## 使用说明

### 1. 日志解析

1. 点击"上传日志"按钮选择 VOBC 二进制日志文件
2. 系统自动检测日志中的数据帧类型
3. 在系统标签中选择要查看的系统
4. 点击"加载"按钮查看解析结果

### 2. 智能巡检

1. 上传日志并选择系统后，切换到"智能巡检"标签页
2. 选择巡检规则
3. 点击"执行巡检"按钮
4. 查看巡检结果（标红：严重异常，标黄：警告）

### 3. 数据绘制

1. 上传日志并选择系统后，切换到"数据绘制"标签页
2. 选择要绘制的字段（支持多选）
3. 选择图表类型（曲线图/直方图/散点图）
4. 点击"绘制图表"按钮
5. 使用鼠标滚轮缩放、拖动查看详细数据

### 4. 案例库

1. 在日志解析页面选择异常数据行
2. 点击"保存案例"按钮
3. 填写故障信息并保存
4. 在"案例库"标签页检索历史案例

## 规则配置

### 巡检规则格式

```json
{
    "name": "ATP应用日检检查",
    "category": "信号系统日检修类",
    "system": "ATP应用",
    "severity": "warning",
    "type": "single_frame",
    "logic": "or",
    "conditions": [
        {"field": "系统", "op": "neq", "value": "0x48"},
        {"field": "序列号", "op": "neq", "value": "166665"}
    ]
}
```

### 操作符支持

| 操作符 | 说明 |
|--------|------|
| `eq` | 等于 |
| `neq` | 不等于 |
| `gt` | 大于 |
| `lt` | 小于 |
| `gte` | 大于等于 |
| `lte` | 小于等于 |
| `contains` | 包含 |

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/upload` | POST | 上传日志文件 |
| `/api/data` | POST | 获取解析数据（分页） |
| `/api/inspect` | POST | 执行巡检 |
| `/api/plot` | POST | 获取绘图数据 |
| `/api/get_fields` | POST | 获取系统字段列表 |
| `/api/cases` | GET/POST | 案例管理 |

## 技术栈

- **后端**：Python 3.10+, FastAPI, SQLite
- **前端**：HTML5, JavaScript, ECharts 5, AG-Grid
- **数据处理**：NumPy, Matplotlib

## 许可证

MIT License
