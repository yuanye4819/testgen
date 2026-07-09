"""
命令行界面 (CLI)
------------------
基于 Click 的命令行入口，提供三个子命令:
  generate       从输入源生成测试用例
  list-formats   列出支持的输入/输出格式
  check          检查环境依赖是否满足

用法示例:
  python -m testgen generate -i api.yaml -s openapi -f pytest
  python -m testgen generate -i ./src/ -s code -f excel -t unit --no-llm
  python -m testgen generate -i requirements.txt -s nl -f json --model gpt-4o
"""

import sys
from pathlib import Path

import click

from .core.models import InputSource, OutputFormat, TestType
from .orchestrator import Orchestrator


INPUT_SOURCE_MAP = {
    "openapi": InputSource.OPENAPI,
    "swagger": InputSource.OPENAPI,
    "code": InputSource.SOURCE_CODE,
    "python": InputSource.SOURCE_CODE,
    "nl": InputSource.NATURAL_LANG,
    "text": InputSource.NATURAL_LANG,
    "url": InputSource.URL,
}

OUTPUT_FORMAT_MAP = {
    "pytest": OutputFormat.PYTEST,
    "json": OutputFormat.JSON,
    "yaml": OutputFormat.YAML,
    "excel": OutputFormat.EXCEL,
    "csv": OutputFormat.CSV,
}

TEST_TYPE_MAP = {
    "api": TestType.API,
    "unit": TestType.UNIT,
    "e2e": TestType.E2E,
    "integration": TestType.INTEGRATION,
    "perf": TestType.PERFORMANCE,
    "functional": TestType.FUNCTIONAL,
}


@click.group()
@click.version_option(version="1.0.0", prog_name="testgen")
def main():
    """
    TestGen - 通用测试用例自动生成系统
    
    支持从 OpenAPI 文档、Python 源代码或自然语言描述中
    自动生成测试用例，输出为 pytest / JSON / YAML / Excel / CSV 格式。
    
    使用 LLM (OpenAI 兼容 API) 增强生成质量，
    也可通过 --no-llm 使用规则模板离线生成。
    """
    pass


@main.command()
@click.option(
    "-i", "--input", "input_path",
    required=True,
    help="输入文件或目录路径",
)
@click.option(
    "-s", "--source",
    type=click.Choice(["openapi", "code", "nl", "url"]),
    default="openapi",
    help="输入来源类型 (openapi/code/nl)",
)
@click.option(
    "-f", "--format", "output_format",
    type=click.Choice(["pytest", "json", "yaml", "excel", "csv"]),
    default="pytest",
    help="输出格式",
)
@click.option(
    "-t", "--type", "test_types",
    multiple=True,
    type=click.Choice(["api", "unit", "e2e", "integration", "perf", "functional"]),
    help="测试类型（可多次指定，如 -t api -t unit）",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="禁用 LLM，使用规则模板生成",
)
@click.option(
    "--model",
    default="gpt-4o",
    help="LLM 模型名称 (默认: gpt-4o)",
)
@click.option(
    "--temperature",
    default=0.3,
    type=float,
    help="LLM 温度参数 (默认: 0.3)",
)
@click.option(
    "-o", "--output-dir",
    default="./output",
    help="输出目录 (默认: ./output)",
)
@click.option(
    "--base-url",
    default="http://localhost:8000",
    help="API 基础 URL (默认: http://localhost:8000)",
)
@click.option(
    "--max-cases",
    default=5,
    type=int,
    help="每个端点的最大生成用例数 (默认: 5)",
)
@click.option(
    "--max-unit-cases",
    default=3,
    type=int,
    help="每个函数的最大生成用例数 (默认: 3)",
)
def generate(
    input_path: str,
    source: str,
    output_format: str,
    test_types: tuple,
    no_llm: bool,
    model: str,
    temperature: float,
    output_dir: str,
    base_url: str,
    max_cases: int,
    max_unit_cases: int,
):
    """
    从指定输入源生成测试用例
    
    支持三种输入源:
      -s openapi  : OpenAPI/Swagger 规范文件（.json / .yaml）
      -s code     : Python 源代码目录或文件
      -s nl       : 自然语言描述文件或文本
    
    支持五种输出格式:
      -f pytest   : 可执行的 pytest 测试文件
      -f json     : JSON 结构化数据
      -f yaml     : YAML 结构化数据
      -f excel    : Excel .xlsx 表格
      -f csv      : CSV 纯文本表格
    
    示例:
      # 从 OpenAPI 文档生成 API 测试用例
      testgen generate -i api.yaml -s openapi -f pytest
    
      # 从 Python 代码生成单元测试
      testgen generate -i ./myproject/ -s code -f pytest -t unit
    
      # 从自然语言描述生成（使用 LLM）
      testgen generate -i requirements.txt -s nl -f excel
    
      # 禁用 LLM 快速生成
      testgen generate -i api.yaml -s openapi -f json --no-llm
    """
    input_source = INPUT_SOURCE_MAP[source]
    fmt = OUTPUT_FORMAT_MAP[output_format]
    types = [TEST_TYPE_MAP[t] for t in test_types] if test_types else []

    orchestrator = Orchestrator()

    result = orchestrator.run(
        input_source=input_source,
        output_format=fmt,
        input_path=input_path,
        test_types=types,
        llm_enabled=not no_llm,
        llm_model=model,
        llm_temperature=temperature,
        output_dir=output_dir,
        base_url=base_url,
        max_cases_per_endpoint=max_cases,
        max_cases_per_function=max_unit_cases,
    )

    if not result["success"]:
        click.echo("[错误] " + result.get('error', '未知错误'), err=True)
        sys.exit(1)

    click.echo(f"\n[完成] 共生成 {result['total_cases']} 个测试用例")


@main.command()
def list_formats():
    """列出所有支持的输入来源、输出格式和测试类型"""
    click.echo("\n[输入] 支持的输入来源:")
    click.echo("  openapi/swagger  - OpenAPI 3.x / Swagger 2.x 规范文件")
    click.echo("  code/python      - Python 源代码目录/文件")
    click.echo("  nl/text          - 自然语言描述文件或文本")

    click.echo("\n[输出] 支持的输出格式:")
    click.echo("  pytest  - 可执行的 pytest Python 测试文件")
    click.echo("  json    - JSON 格式测试用例描述")
    click.echo("  yaml    - YAML 格式测试用例描述")
    click.echo("  excel   - Excel .xlsx 表格（带优先级着色）")
    click.echo("  csv     - CSV 纯文本表格")

    click.echo("\n[类型] 支持的测试类型:")
    click.echo("  api, unit, e2e, integration, perf")


@main.command()
def check():
    """
    检查环境依赖是否满足运行要求
    
    检查项:
      - Python 版本（>= 3.10）
      - 核心依赖包（openpyxl, PyYAML, Jinja2, OpenAI SDK, Click）
      - 环境变量（OPENAI_API_KEY, OPENAI_BASE_URL）
    """
    click.echo("[检查] 检查环境...\n")

    checks = []

    # Python 版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    checks.append(("Python 版本", py_ver, py_ok))

    # openpyxl
    try:
        import openpyxl  # noqa
        checks.append(("openpyxl (Excel)", "已安装", True))
    except ImportError:
        checks.append(("openpyxl (Excel)", "未安装", False))

    # yaml
    try:
        import yaml  # noqa
        checks.append(("PyYAML", "已安装", True))
    except ImportError:
        checks.append(("PyYAML", "未安装", False))

    # jinja2
    try:
        import jinja2  # noqa
        checks.append(("Jinja2", "已安装", True))
    except ImportError:
        checks.append(("Jinja2", "未安装", False))

    # openai
    try:
        import openai  # noqa
        checks.append(("OpenAI SDK", "已安装", True))
    except ImportError:
        checks.append(("OpenAI SDK", "未安装 (LLM 模式不可用)", False))

    # click (already imported, just verify)
    checks.append(("Click", "已安装", True))

    # 环境变量
    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    checks.append(("OPENAI_API_KEY", "已设置" if api_key else "未设置 (LLM 模式不可用)", bool(api_key)))

    base_url = os.environ.get("OPENAI_BASE_URL")
    checks.append(("OPENAI_BASE_URL", base_url or "未设置 (使用默认)", True))

    # 打印
    for name, value, ok in checks:
        icon = "[OK]" if ok else "[!!]"
        click.echo(f"  {icon} {name}: {value}")

    click.echo("\n[提示] 安装缺失依赖: pip install -r requirements.txt")


if __name__ == "__main__":
    main()
