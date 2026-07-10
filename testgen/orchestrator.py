"""
主协调器 (Orchestrator)
-------------------------
串联 解析 → 生成 → 输出 全流程的顶层控制器。

职责:
  1. 根据 input_source 选择对应的解析器
  2. 调用生成器（LLM 或规则模式）
  3. 根据 output_format 选择对应的输出适配器
  4. 打印流程摘要（found端点数、生成用例数、输出文件列表）

设计意图:
  协调器不包含任何解析/生成/输出逻辑，
  所有具体工作委托给对应的插件模块。
  新增功能只需注册新的 Parser / Generator / Adapter 即可。
"""

from pathlib import Path
from typing import Optional

from .core.models import (
    GenerationContext,
    InputSource,
    OutputFormat,
    TestType,
)
from .parsers.openapi_parser import OpenAPIParser
from .parsers.code_parser import CodeParser
from .parsers.natural_lang_parser import NaturalLangParser
from .generators.generator import TestCaseGenerator
from .outputs.pytest_adapter import PytestAdapter
from .outputs.json_adapter import JSONAdapter, YAMLAdapter
from .outputs.excel_adapter import ExcelAdapter, CSVAdapter


class Orchestrator:
    """
    测试用例生成系统的总调度器
    
    持有所有解析器、生成器、输出适配器的注册表。
    新增模块只需在相应的字典中注册即可生效。
    """

    def __init__(self):
        self._parsers = {
            InputSource.OPENAPI: OpenAPIParser(),
            InputSource.SOURCE_CODE: CodeParser(),
            InputSource.NATURAL_LANG: NaturalLangParser(),
            InputSource.URL: NaturalLangParser(),
        }
        self._generator = TestCaseGenerator()
        self._output_adapters = {
            OutputFormat.PYTEST: PytestAdapter(),
            OutputFormat.JSON: JSONAdapter(),
            OutputFormat.YAML: YAMLAdapter(),
            OutputFormat.EXCEL: ExcelAdapter(),
            OutputFormat.CSV: CSVAdapter(),
        }

    def run(
        self,
        input_source: InputSource,
        output_format: OutputFormat,
        input_path: str = "",
        test_types: Optional[list[TestType]] = None,
        llm_enabled: bool = True,
        llm_model: str = "gpt-4o",
        llm_temperature: float = 0.3,
        output_dir: str = "./output",
        base_url: str = "http://localhost:8000",
        max_cases_per_endpoint: int = 5,
        max_cases_per_function: int = 3,
    ) -> dict:
        """
        执行完整的测试用例生成流程
        
        流程: 构建上下文 → 解析输入 → 生成用例 → 输出文件
        
        Args:
            input_source:           输入来源类型（openapi / code / nl）
            output_format:          输出格式（pytest / json / yaml / excel / csv）
            input_path:             输入文件/目录路径
            test_types:             要生成的测试类型（空则自动推断）
            llm_enabled:            是否启用 LLM（False 用规则模板）
            llm_model:              LLM 模型名
            llm_temperature:        LLM 温度参数（0-1，越低越确定）
            output_dir:             输出目录
            base_url:               API 基础 URL
            max_cases_per_endpoint: 每API endpoints最大生成用例数
            max_cases_per_function: 每functions最大生成用例数
        
        Returns:
            {
                "success":       bool,          # 是否成功
                "suites_count":  int,           # 生成的套件数量
                "total_cases":   int,           # 总测试用例数
                "output_files":  [str, ...],    # 输出文件路径列表
                "error":         str (仅失败时)  # 错误信息
            }
        """
        # 1. 构建上下文
        context = GenerationContext(
            input_source=input_source,
            output_format=output_format,
            test_types=test_types or [],
            raw_input=input_path,
            llm_enabled=llm_enabled,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            output_dir=output_dir,
            base_url=base_url,
            max_cases_per_endpoint=max_cases_per_endpoint,
            max_cases_per_function=max_cases_per_function,
        )

        # 2. 解析输入
        parser = self._parsers.get(input_source)
        if parser is None:
            return {"success": False, "error": f"Unsupported input source: {input_source.value}"}

        print(f"\n[Parse] source={input_source.value}")
        try:
            context = parser.parse(context)
        except Exception as e:
            return {"success": False, "error": f"Parse failed: {e}"}

        # 打印解析结果摘要
        # self._print_parse_summary(context)  # skip to avoid GBK errors

        # 3. 生成测试用例
        print(f"\n[Generate] LLM={'启用' if llm_enabled else '关闭'})...")
        try:
            suites = self._generator.generate(context)
        except Exception as e:
            return {"success": False, "error": f"Generation failed: {e}"}

        total_cases = sum(s.total_cases for s in suites)
        print(f"  OK generated {len(suites)}  suites,  {total_cases}  cases")

        # 4. 输出
        print(f"\n[Output] {output_format.value})...")
        adapter = self._output_adapters.get(output_format)
        if adapter is None:
            return {"success": False, "error": f"Unsupported output format: {output_format.value}"}

        try:
            output_files = adapter.write(suites, context)
        except Exception as e:
            return {"success": False, "error": f"Output failed: {e}"}

        print(f"  OK generated {len(output_files)}  files")
        for f in output_files:
            print(f"    → {f}")

        return {
            "success": True,
            "suites_count": len(suites),
            "total_cases": total_cases,
            "output_files": output_files,
        }

    def _print_parse_summary(self, context: GenerationContext):
        """
        打印解析结果摘要
        
        输出格式:
          found N API endpoints
            - METHOD  path
          （最多展示前 5 条，超出提示总数）
        """
        if context.api_endpoints:
            methods = set(e.method.value for e in context.api_endpoints)
            print(f"  OK found {len(context.api_endpoints)} API endpoints")
            for ep in context.api_endpoints[:5]:
                print(f"    - {ep.method.value:6s} {ep.path}")
            if len(context.api_endpoints) > 5:
                print(f"    ... + {len(context.api_endpoints) - 5} 个")

        if context.functions:
            print(f"  OK found {len(context.functions)} functions")
            for f in context.functions[:5]:
                print(f"    - {f.name} (complexity: {f.complexity})")
            if len(context.functions) > 5:
                print(f"    ... + {len(context.functions) - 5} 个")

        if context.classes:
            print(f"  OK found {len(context.classes)} classes")
            for c in context.classes[:5]:
                print(f"    - {c.name} ({len(c.methods)} methods)")
            if len(context.classes) > 5:
                print(f"    ... + {len(context.classes) - 5} 个")

        if context.natural_lang_desc:
            preview = context.natural_lang_desc[:100].replace("\n", " ")
            print(f"  OK NL desc: {preview}...")
