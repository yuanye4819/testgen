"""
Prompt 构建器
--------------
根据解析结果，针对不同测试类型构建结构化的 LLM 提示词。

设计原则:
  - 每种测试类型有专用的 build 方法
  - SYSTEM_PROMPT_BASE 定义角色和输出格式要求
  - user prompt 包含完整的上下文（参数、请求体、响应 schema、源码等）
  - 引导 LLM 输出结构化 JSON（覆盖正常/边界/异常场景）
"""

from ..core.models import (
    GenerationContext,
    APIEndpoint,
    FunctionDef,
    TestType,
)


class PromptBuilder:
    """
    为不同类型的测试用例构建 LLM 提示词
    
    三个核心方法:
      build_api_prompt()        → 为 API 端点生成测试用例的 prompt
      build_unit_prompt()       → 为函数生成单元测试的 prompt
      build_natural_lang_prompt() → 为自然语言描述生成测试用例的 prompt
    """

    SYSTEM_PROMPT_BASE = """你是一个专业的测试工程师，擅长根据需求生成高质量的测试用例。
生成的测试用例应该：
1. 覆盖正常情况和边界情况
2. 包含清晰的前置条件和测试步骤
3. 每个步骤有明确的预期结果
4. 标注优先级（high/medium/low）

请以 JSON 格式返回，结构如下：
{
  "test_cases": [
    {
      "name": "测试用例名称",
      "description": "详细描述",
      "priority": "high|medium|low",
      "tags": ["标签1", "标签2"],
      "preconditions": ["前置条件1"],
      "steps": [
        {"step_number": 1, "action": "操作步骤", "expected_result": "预期结果", "assertions": ["断言1"]}
      ],
      "expected_status": 200,
      "expected_response": {}
    }
  ]
}"""

    def build_api_prompt(self, endpoint: APIEndpoint, context: GenerationContext) -> str:
        """为单个 API 端点构建 prompt"""
        params_desc = self._describe_parameters(endpoint.parameters)
        request_body_desc = self._describe_request_body(endpoint.request_body)
        responses_desc = self._describe_responses(endpoint.responses)

        return f"""请为以下 API 端点生成 {context.max_cases_per_endpoint} 个测试用例：

**HTTP 方法**: {endpoint.method.value}
**路径**: {endpoint.path}
**描述**: {endpoint.description or endpoint.summary}
**标签**: {', '.join(endpoint.tags) if endpoint.tags else '无'}

**参数**:
{params_desc}

**请求体**:
{request_body_desc}

**响应定义**:
{responses_desc}

请生成覆盖以下场景的测试用例：
- 正常请求成功返回
- 参数校验失败（缺少必填参数、参数类型错误）
- 边界值测试
- 异常情况（如资源不存在、权限不足）
- 请求体校验失败"""

    def build_unit_prompt(self, func: FunctionDef, context: GenerationContext) -> str:
        """为单个函数/方法构建 prompt"""
        params_desc = "\n".join(
            f"  - {p.name}: {p.schema.get('type', 'Any') if p.schema else 'Any'}"
            f" {'(可选, 默认=' + str(p.default) + ')' if not p.required and p.default else ''}"
            for p in func.parameters
        ) if func.parameters else "  无参数"

        return_type = func.return_type or "Any"
        source = func.source_code[:2000] if func.source_code else "（无源码）"

        return f"""请为以下函数生成 {context.max_cases_per_function} 个单元测试用例：

**函数名**: {func.name}
**模块**: {func.module}
**文档**: {func.docstring or '无'}
**参数**:
{params_desc}
**返回类型**: {return_type}
**圈复杂度**: {func.complexity}

**源码**:
```python
{source}
```

请生成覆盖以下场景的测试用例：
- 正常输入，验证返回值
- 边界值/空值输入
- 异常输入（类型错误、越界等）
- 如果有副作用（IO、网络），考虑 mock 方案"""

    def build_natural_lang_prompt(self, context: GenerationContext) -> str:
        """为自然语言描述构建 prompt"""
        test_types_str = ", ".join(t.value for t in context.test_types)
        return f"""请根据以下需求描述生成测试用例：

**测试类型**: {test_types_str}
**需求描述**:
{context.natural_lang_desc[:4000]}

请生成覆盖以下方面的测试用例：
- 功能验证（正常流程）
- 边界条件
- 异常处理
- 性能/安全考虑（如适用）

每种测试类型至少生成 3 个测试用例。"""

    def _describe_parameters(self, parameters: list) -> str:
        """
        格式化参数列表为可读文本
        
        输出格式: - name [param_type] (必填/可选) (描述) (示例: xxx)
        """
        if not parameters:
            return "  无参数"
        lines = []
        for p in parameters:
            required = "必填" if p.required else "可选"
            desc = f" ({p.description})" if p.description else ""
            example = f" (示例: {p.example})" if p.example else ""
            lines.append(f"  - {p.name} [{p.param_type}] ({required}){desc}{example}")
        return "\n".join(lines)

    def _describe_request_body(self, request_body: dict | None) -> str:
        """格式化请求体 JSON Schema 为缩进 JSON 文本"""
        if not request_body:
            return "  无请求体"
        import json
        return json.dumps(request_body, indent=2, ensure_ascii=False)

    def _describe_responses(self, responses: dict) -> str:
        """格式化响应定义为可读文本，截断过长 schema"""
        if not responses:
            return "  未定义"
        lines = []
        for status, info in responses.items():
            desc = info.get("description", "")
            schema = info.get("content")
            schema_str = ""
            if schema:
                import json
                schema_str = f"\n    Schema: {json.dumps(schema, indent=4, ensure_ascii=False)[:500]}"
            lines.append(f"  HTTP {status}: {desc}{schema_str}")
        return "\n".join(lines)
