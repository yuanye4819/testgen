"""
JSON / YAML 输出适配器
------------------------
将测试套件序列化为结构化数据文件。

JSONAdapter:
  - 每个 suite 一个 .json 文件
  - 多套件时自动生成 _all_test_suites.json 合并文件
  - UTF-8 + ensure_ascii=False（中文直接可读）

YAMLAdapter:
  - 每个 suite 一个 .yaml 文件
  - block style 输出，易读易编辑
"""

import json
from datetime import datetime
from pathlib import Path

from ..core.base import BaseOutputAdapter
from ..core.models import GenerationContext, TestSuite, OutputFormat


class JSONAdapter(BaseOutputAdapter):
    """生成 JSON 格式的测试用例文件（见模块文档了解详情）"""

    def format_name(self) -> str:
        return "json"

    def write(self, suites: list[TestSuite], context: GenerationContext) -> list[str]:
        output_dir = Path(context.output_dir) / "json"
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files: list[str] = []

        for suite in suites:
            filename = self._sanitize(suite.name) + ".json"
            filepath = output_dir / filename
            data = self._suite_to_dict(suite)
            filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            generated_files.append(str(filepath))

        if len(suites) > 1:
            all_data = [self._suite_to_dict(s) for s in suites]
            merged_path = output_dir / "_all_test_suites.json"
            merged_path.write_text(json.dumps(all_data, indent=2, ensure_ascii=False), encoding="utf-8")
            generated_files.append(str(merged_path))

        return generated_files

    def _suite_to_dict(self, suite: TestSuite) -> dict:
        return {
            "suite_name": suite.name,
            "description": suite.description,
            "total_cases": suite.total_cases,
            "generation_time": datetime.now().isoformat(),
            "test_cases": [self._case_to_dict(c) for c in suite.test_cases],
        }

    def _case_to_dict(self, case) -> dict:
        result = {
            "id": case.id,
            "name": case.name,
            "description": case.description,
            "test_type": case.test_type.value,
            "priority": case.priority,
            "tags": case.tags,
            "preconditions": case.preconditions,
            "expected_result": case.expected_result,
            "steps": [
                {
                    "step_number": s.step_number,
                    "action": s.action,
                    "expected_result": s.expected_result,
                    "assertions": s.assertions,
                }
                for s in case.steps
            ],
            "expected_status": case.expected_status,
        }
        if case.expected_response:
            result["expected_response"] = case.expected_response
        if case.expected_error:
            result["expected_error"] = case.expected_error
        return result

    def _sanitize(self, name: str) -> str:
        import re
        return re.sub(r'[<>:"/\\|?*]', "_", name).replace(" ", "_")


class YAMLAdapter(BaseOutputAdapter):
    """生成 YAML 格式的测试用例文件（见模块文档了解详情）"""

    def format_name(self) -> str:
        return "yaml"

    def write(self, suites: list[TestSuite], context: GenerationContext) -> list[str]:
        try:
            import yaml
        except ImportError:
            raise ImportError("请安装 pyyaml: pip install pyyaml")

        output_dir = Path(context.output_dir) / "yaml"
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files: list[str] = []

        for suite in suites:
            filename = self._sanitize(suite.name) + ".yaml"
            filepath = output_dir / filename
            data = self._suite_to_dict(suite)
            filepath.write_text(
                yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
            generated_files.append(str(filepath))

        return generated_files

    def _suite_to_dict(self, suite: TestSuite) -> dict:
        return {
            "suite_name": suite.name,
            "description": suite.description,
            "total_cases": suite.total_cases,
            "generation_time": datetime.now().isoformat(),
            "test_cases": [self._case_to_dict(c) for c in suite.test_cases],
        }

    def _case_to_dict(self, case) -> dict:
        result = {
            "id": case.id,
            "name": case.name,
            "description": case.description,
            "test_type": case.test_type.value,
            "priority": case.priority,
            "tags": case.tags,
            "preconditions": case.preconditions,
            "expected_result": case.expected_result,
            "steps": [
                {
                    "step_number": s.step_number,
                    "action": s.action,
                    "expected_result": s.expected_result,
                    "assertions": s.assertions,
                }
                for s in case.steps
            ],
            "expected_status": case.expected_status,
        }
        if case.expected_response:
            result["expected_response"] = case.expected_response
        if case.expected_error:
            result["expected_error"] = case.expected_error
        return result

    def _sanitize(self, name: str) -> str:
        import re
        return re.sub(r'[<>:"/\\|?*]', "_", name).replace(" ", "_")
