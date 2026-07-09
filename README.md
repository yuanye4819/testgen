# TestGen — 通用测试用例自动生成系统

从 OpenAPI / 源代码 / 自然语言描述中自动生成测试用例，支持 LLM 增强。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 检查环境
python -m testgen check

# 生成示例（从 OpenAPI）
python -m testgen generate -i sample_api.yaml -s openapi -f pytest --no-llm -o ./output

# 使用 LLM 增强（需设置 OPENAI_API_KEY）
python -m testgen generate -i api.yaml -s openapi -f pytest
```

## 支持的输入

| 来源 | 命令参数 | 说明 |
|------|----------|------|
| OpenAPI 3.x / Swagger | `-s openapi` | JSON/YAML 规范文件 |
| Python 源代码 | `-s code` | 自动提取函数/类/方法 |
| 自然语言 | `-s nl` | 需求描述文本 |

## 支持的输出

| 格式 | 命令参数 | 说明 |
|------|----------|------|
| pytest | `-f pytest` | 可执行的 Python 测试文件 |
| JSON | `-f json` | 结构化 JSON 测试用例 |
| YAML | `-f yaml` | 人类可读的 YAML |
| Excel | `-f excel` | .xlsx 表格（带着色） |
| CSV | `-f csv` | 纯文本表格 |

## 目录结构

```
testgen/
├── core/           # 数据模型 + 抽象基类
├── parsers/        # 输入解析器
├── generators/     # 生成引擎（LLM + 模板）
├── outputs/        # 输出适配器
├── orchestrator.py # 总调度协调器
└── cli.py          # 命令行入口
user_data/docs/     # 设计文档
```

## 环境变量

```bash
OPENAI_API_KEY="sk-xxx"              # 必需（LLM 模式）
OPENAI_BASE_URL="http://..."         # 可选：自定义 API 端点
```
