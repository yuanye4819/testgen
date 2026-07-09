"""
模板引擎
---------
基于 Jinja2 的模板渲染引擎，用于规则模式下生成测试代码。

特性:
  - 从 templates/ 目录加载模板文件
  - 支持字符串模板直接渲染
  - 首次使用时自动创建默认模板（pytest / json）
  - 与 LLM 模式互补：LLM 失败时用模板兜底
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template


class TemplateEngine:
    """
    Jinja2 模板引擎封装
    
    用法:
        engine = TemplateEngine()
        engine.ensure_default_templates()  # 首次使用
        output = engine.render("pytest_template.j2", context)
    """

    def __init__(self, template_dir: str = "templates"):
        template_path = Path(template_dir)
        template_path.mkdir(parents=True, exist_ok=True)

        self._env = Environment(
            loader=FileSystemLoader(str(template_path)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template_dir = template_path

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        """
        渲染指定名称的模板文件
        
        Args:
            template_name: templates/ 目录下的文件名
            context:       模板变量字典
        Returns:
            渲染后的字符串
        """
        template = self._env.get_template(template_name)
        return template.render(**context)

    def render_string(self, template_string: str, context: dict[str, Any]) -> str:
        """
        直接渲染字符串模板（无需模板文件）
        
        Args:
            template_string: Jinja2 模板字符串
            context:         模板变量字典
        Returns:
            渲染后的字符串
        """
        template = Template(template_string)
        return template.render(**context)

    def ensure_default_templates(self):
        """
        确保 templates/ 目录下存在默认模板文件
        
        仅在文件不存在时创建，不会覆盖用户自定义的模板。
        默认提供:
          - pytest_template.j2  : pytest 测试文件模板
          - json_template.j2    : JSON 测试用例模板
        """
        default_templates = {
            "pytest_template.j2": '''"""
{{ suite.name }} - 自动生成的测试用例
生成时间: {{ generation_time }}
"""
import pytest
{% if suite.setup_code %}
{{ suite.setup_code }}
{% endif %}

{% for case in suite.test_cases %}
class Test{{ case.name | replace(" ", "_") | replace("-", "_") }}:
    """{{ case.description or case.name }}"""

{% if case.preconditions %}
    # 前置条件:
{% for p in case.preconditions %}
    #   - {{ p }}
{% endfor %}
{% endif %}

{% for step in case.steps %}
    def test_step_{{ step.step_number }}_{{ step.action | truncate(30, True, "") | replace(" ", "_") | replace("-", "_") | lower }}(self):
        """{{ step.action }}"""
        # 预期: {{ step.expected_result }}
{% for assertion in step.assertions %}
        # 断言: {{ assertion }}
{% endfor %}
        pass

{% endfor %}
{% endfor %}
{% if suite.teardown_code %}
# Teardown
{{ suite.teardown_code }}
{% endif %}
''',
            "json_template.j2": '''{
  "suite_name": "{{ suite.name }}",
  "description": "{{ suite.description }}",
  "generation_time": "{{ generation_time }}",
  "test_cases": [
{% for case in suite.test_cases %}
    {
      "id": "{{ case.id }}",
      "name": "{{ case.name }}",
      "description": "{{ case.description }}",
      "priority": "{{ case.priority }}",
      "tags": {{ case.tags | tojson }},
      "preconditions": {{ case.preconditions | tojson }},
      "steps": [
{% for step in case.steps %}
        {
          "step_number": {{ step.step_number }},
          "action": "{{ step.action }}",
          "expected_result": "{{ step.expected_result }}",
          "assertions": {{ step.assertions | tojson }}
        }{% if not loop.last %},{% endif %}
{% endfor %}
      ]
    }{% if not loop.last %},{% endif %}
{% endfor %}
  ]
}''',
        }

        for name, content in default_templates.items():
            path = self._template_dir / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")
