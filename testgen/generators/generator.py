"""
主测试用例生成器
--------------------
协调 LLM 智能生成与规则模板回退两种模式。

LLM 模式:
  入口 → _generate_with_llm() → 按类型分发 → PromptBuilder 构建提示词
  → LLMClient.chat_json() → _parse_llm_response() 解析 JSON → TestSuite[]
  
  优点: 智能分析源码/API，生成真实场景的测试用例
  缺点: 依赖网络和 API Key，有成本

规则模式 (--no-llm):
  入口 → _generate_api_rules / _generate_unit_rules → 预定义规则
  → _fallback_*_cases() → TestSuite[]
  
  优点: 离线可用，即时响应，适合快速生成骨架
  缺点: 用例较简单，无法深入理解业务逻辑

异常处理策略:
  LLM 生成失败时自动回退到对应 _fallback_* 方法，
  确保即使 LLM 不可用也能输出可用的测试骨架。
"""

from datetime import datetime

from ..core.base import BaseGenerator
from ..core.models import (
    GenerationContext,
    TestSuite,
    TestCase,
    TestStep,
    TestType,
)
from .llm_client import LLMClient
from .prompt_builder import PromptBuilder
from .template_engine import TemplateEngine


class TestCaseGenerator(BaseGenerator):
    """测试用例生成器：支持 LLM 模式和规则模板模式"""

    def __init__(self):
        self.llm_client = LLMClient()
        self.prompt_builder = PromptBuilder()
        self.template_engine = TemplateEngine()

    def generate(self, context: GenerationContext) -> list[TestSuite]:
        """
        主生成入口
        
        根据 context.llm_enabled 自动选择 LLM 模式或规则模式。
        LLM 模式下单个端点生成失败不会中断整体流程，会自动回退。
        """
        suites: list[TestSuite] = []

        if context.llm_enabled:
            return self._generate_with_llm(context)

        # 非 LLM 模式：基于模板规则生成
        for test_type in context.test_types:
            if test_type == TestType.API:
                suites.append(self._generate_api_rules(context))
            elif test_type == TestType.UNIT:
                suites.append(self._generate_unit_rules(context))
            elif test_type == TestType.E2E:
                suites.append(self._generate_e2e_rules(context))
            else:
                suites.append(self._generate_generic_rules(context, test_type))

        return suites

    def _generate_with_llm(self, context: GenerationContext) -> list[TestSuite]:
        """
        LLM 模式：逐类型分发到专门的 LLM 生成方法
        
        每个 test_type 走独立分支：
          API  → _generate_api_with_llm()   (逐端点调用 LLM)
          UNIT → _generate_unit_with_llm()  (逐函数调用 LLM)
          其他 → _generate_generic_with_llm()
        """
        """使用 LLM 生成测试用例"""
        suites: list[TestSuite] = []

        for test_type in context.test_types:
            if test_type == TestType.API:
                suites.extend(self._generate_api_with_llm(context))
            elif test_type == TestType.UNIT:
                suites.extend(self._generate_unit_with_llm(context))
            else:
                suite = self._generate_generic_with_llm(context, test_type)
                if suite:
                    suites.append(suite)

        return suites

    # ─── LLM 模式 ───────────────────────────────────────

    def _generate_api_with_llm(self, context: GenerationContext) -> list[TestSuite]:
        """
        为每个 API 端点调用 LLM 生成测试用例
        
        流程: 遍历 api_endpoints → PromptBuilder.build_api_prompt()
        → LLMClient.chat_json() → _parse_llm_response()
        
        每个端点生成一个独立的 TestSuite，命名格式: API_{METHOD}_{path}
        单个端点失败不影响其他端点，自动回退到 _fallback_api_cases()
        """
        suites = []
        for endpoint in context.api_endpoints:
            prompt = self.prompt_builder.build_api_prompt(endpoint, context)
            try:
                result = self.llm_client.chat_json(
                    context,
                    system_prompt=self.prompt_builder.SYSTEM_PROMPT_BASE,
                    user_prompt=prompt,
                )
                cases = self._parse_llm_response(result, TestType.API, endpoint)
            except Exception as e:
                print(f"  ⚠ LLM 生成失败 ({endpoint.method.value} {endpoint.path}): {e}")
                cases = self._fallback_api_cases(endpoint, context)

            suite = TestSuite(
                name=f"API_{endpoint.method.value}_{endpoint.path.replace('/', '_')}",
                description=endpoint.description or endpoint.summary,
                test_cases=cases,
            )
            suites.append(suite)
        return suites

    def _generate_unit_with_llm(self, context: GenerationContext) -> list[TestSuite]:
        """
        为每个函数调用 LLM 生成单元测试用例
        
        自动跳过私有函数（以 _ 开头），但保留 __init__。
        每个函数生成一个独立 TestSuite，命名格式: Test_{func.name}
        """
        suites = []
        for func in context.functions:
            if func.name.startswith("_") and not func.name.startswith("__init__"):
                continue
            prompt = self.prompt_builder.build_unit_prompt(func, context)
            try:
                result = self.llm_client.chat_json(
                    context,
                    system_prompt=self.prompt_builder.SYSTEM_PROMPT_BASE,
                    user_prompt=prompt,
                )
                cases = self._parse_llm_response(result, TestType.UNIT, func)
            except Exception as e:
                print(f"  ⚠ LLM 生成失败 ({func.name}): {e}")
                cases = self._fallback_unit_cases(func, context)

            suite = TestSuite(
                name=f"Test_{func.name}",
                description=func.docstring,
                test_cases=cases,
            )
            suites.append(suite)
        return suites

    def _generate_generic_with_llm(
        self, context: GenerationContext, test_type: TestType
    ) -> TestSuite | None:
        """
        为自然语言描述等非结构化输入调用 LLM 生成
        
        使用 build_natural_lang_prompt() 构建 prompt，
        LLM 失败时回退到 _fallback_generic_cases()
        """
        prompt = self.prompt_builder.build_natural_lang_prompt(context)
        try:
            result = self.llm_client.chat_json(
                context,
                system_prompt=self.prompt_builder.SYSTEM_PROMPT_BASE,
                user_prompt=prompt,
            )
            cases = self._parse_llm_response(result, test_type)
        except Exception as e:
            print(f"  ⚠ LLM 生成失败: {e}")
            cases = self._fallback_generic_cases(context, test_type)

        return TestSuite(
            name=f"{test_type.value}_tests",
            description=context.natural_lang_desc[:200],
            test_cases=cases,
        )

    def _parse_llm_response(
        self, result: dict, test_type: TestType, source: object = None
    ) -> list[TestCase]:
        """
        解析 LLM 返回的 JSON 为 TestCase 列表
        
        LLM 返回格式:
          {"test_cases": [{name, description, priority, steps: [{action, expected_result, ...}], ...}]}
        
        Args:
            result:     LLM JSON 响应（已反序列化）
            test_type:  将赋给每个 TestCase 的类型标记
            source:     可选的回填引用（APIEndpoint 或 FunctionDef）
        """
        raw_cases = result.get("test_cases", [])
        cases = []
        for i, rc in enumerate(raw_cases):
            steps = [
                TestStep(
                    step_number=s.get("step_number", j + 1),
                    action=s.get("action", ""),
                    expected_result=s.get("expected_result", ""),
                    data=s.get("data"),
                    assertions=s.get("assertions", []),
                )
                for j, s in enumerate(rc.get("steps", []))
            ]

            tc = TestCase(
                id=rc.get("id", f"{test_type.value}_{i+1:03d}"),
                name=rc.get("name", f"Test Case {i+1}"),
                description=rc.get("description", ""),
                test_type=test_type,
                tags=rc.get("tags", []),
                priority=rc.get("priority", "medium"),
                preconditions=rc.get("preconditions", []),
                steps=steps,
                expected_status=rc.get("expected_status", 200),
                expected_response=rc.get("expected_response"),
                expected_error=rc.get("expected_error"),
            )
            cases.append(tc)
        return cases

    # ═══════════════════════════════════════════════════════════
    # 规则模板模式（回退方案）
    # 以下方法在 --no-llm 或 LLM 调用失败时使用。
    # 基于预设规则快速生成测试用例骨架。
    # ═══════════════════════════════════════════════════════════

    def _generate_api_rules(self, context: GenerationContext) -> TestSuite:
        """
        规则模式：为所有 API 端点生成一个合并的 TestSuite
        """
        all_cases = []
        for endpoint in context.api_endpoints:
            all_cases.extend(self._fallback_api_cases(endpoint, context))
        # 没有解析到端点时，回退到通用规则
        if not all_cases:
            all_cases = self._fallback_generic_cases(context, TestType.API)
        return TestSuite(
            name="API_Tests",
            description="基于规则生成的 API 测试用例",
            test_cases=all_cases,
        )

    def _generate_unit_rules(self, context: GenerationContext) -> TestSuite:
        """
        规则模式：为所有函数生成一个合并的 TestSuite
        """
        all_cases = []
        for func in context.functions:
            if func.name.startswith("_") and not func.name.startswith("__init__"):
                continue
            all_cases.extend(self._fallback_unit_cases(func, context))
        # 没有解析到函数时，回退到通用规则
        if not all_cases:
            all_cases = self._fallback_generic_cases(context, TestType.UNIT)
        return TestSuite(
            name="Unit_Tests",
            description="基于规则生成的单元测试用例",
            test_cases=all_cases,
        )

    def _generate_e2e_rules(self, context: GenerationContext) -> TestSuite:
        """规则模式：生成 E2E 测试用例骨架"""
        return TestSuite(
            name="E2E_Tests",
            description="基于规则生成的 E2E 测试用例",
            test_cases=self._fallback_generic_cases(context, TestType.E2E),
        )

    def _generate_generic_rules(
        self, context: GenerationContext, test_type: TestType
    ) -> TestSuite:
        """规则模式：为其他测试类型生成通用用例骨架"""
        return TestSuite(
            name=f"{test_type.value}_Tests",
            description=context.natural_lang_desc[:200],
            test_cases=self._fallback_generic_cases(context, test_type),
        )

    def _fallback_api_cases(
        self, endpoint: 'APIEndpoint', context: GenerationContext
    ) -> list[TestCase]:
        """
        API 规则模板核心逻辑
        
        生成策略:
          - 始终生成"正常请求"用例（必须）
          - 如有必填参数 → 生成"缺少必填参数"用例
          - 如定义 requestBody → 生成"空请求体"用例
        
        结果通过 context.max_cases_per_endpoint 截断。
        """
        cases = []
        base_name = f"{endpoint.method.value} {endpoint.path}"

        # 正常请求
        required_params = [p for p in endpoint.parameters if p.required]
        cases.append(TestCase(
            id=f"api_{endpoint.method.value}_{endpoint.path.replace('/', '_')}_ok",
            name=f"{base_name} - 正常请求",
            description=f"使用合法参数调用 {endpoint.path}",
            test_type=TestType.API,
            tags=endpoint.tags + ["smoke"],
            priority="high",
            preconditions=["服务正常运行"],
            steps=[
                TestStep(
                    step_number=1,
                    action=f"发送 {endpoint.method.value} 请求到 {endpoint.path}，携带合法参数",
                    expected_result=f"返回 HTTP 200，响应结构正确",
                    assertions=[
                        "状态码为 200",
                        "响应体为有效 JSON",
                    ],
                )
            ],
            endpoint=endpoint,
            expected_status=200,
        ))

        # 参数缺失
        if required_params:
            missing = required_params[0]
            cases.append(TestCase(
                id=f"api_{endpoint.method.value}_{endpoint.path.replace('/', '_')}_missing_param",
                name=f"{base_name} - 缺少必填参数: {missing.name}",
                description="验证缺少必填参数时的错误处理",
                test_type=TestType.API,
                tags=endpoint.tags + ["validation"],
                priority="high",
                preconditions=[],
                steps=[
                    TestStep(
                        step_number=1,
                        action=f"发送 {endpoint.method.value} 请求到 {endpoint.path}，不传 {missing.name} 参数",
                        expected_result="返回 4xx 错误，提示缺少必填参数",
                        assertions=["状态码为 400 或 422"],
                    )
                ],
                endpoint=endpoint,
                expected_status=400,
            ))

        # 请求体为空
        if endpoint.request_body:
            cases.append(TestCase(
                id=f"api_{endpoint.method.value}_{endpoint.path.replace('/', '_')}_empty_body",
                name=f"{base_name} - 空请求体",
                description="验证空请求体的处理",
                test_type=TestType.API,
                tags=endpoint.tags + ["validation"],
                priority="medium",
                steps=[
                    TestStep(
                        step_number=1,
                        action=f"发送 {endpoint.method.value} 请求到 {endpoint.path}，请求体为空",
                        expected_result="返回 4xx 验证错误",
                        assertions=["状态码为 400 或 422"],
                    )
                ],
                endpoint=endpoint,
                expected_status=400,
            ))

        return cases[:context.max_cases_per_endpoint]

    def _fallback_unit_cases(
        self, func: 'FunctionDef', context: GenerationContext
    ) -> list[TestCase]:
        """
        单元测试规则模板核心逻辑
        
        生成策略:
          - 始终生成"正常调用"用例
          - 如有参数 → 生成"边界值测试"用例
          - 如圈复杂度 >= 3 → 生成"异常输入"用例（高复杂度函数更需异常覆盖）
        
        结果通过 context.max_cases_per_function 截断。
        """
        cases = []

        # 正常调用
        cases.append(TestCase(
            id=f"unit_{func.name}_normal",
            name=f"{func.name} - 正常调用",
            description=f"使用合法参数调用 {func.name}",
            test_type=TestType.UNIT,
            tags=["unit", func.module],
            priority="high",
            preconditions=["所有依赖可用"],
            steps=[
                TestStep(
                    step_number=1,
                    action=f"调用 {func.name}，传入合法参数",
                    expected_result="返回预期结果，无异常",
                )
            ],
            function=func,
        ))

        # 边界值 - 空输入
        if func.parameters:
            cases.append(TestCase(
                id=f"unit_{func.name}_boundary",
                name=f"{func.name} - 边界值测试",
                description=f"使用边界值/空值参数调用 {func.name}",
                test_type=TestType.UNIT,
                tags=["unit", func.module, "boundary"],
                priority="medium",
                steps=[
                    TestStep(
                        step_number=1,
                        action=f"调用 {func.name}，传入 None/空值",
                        expected_result="根据实现返回空结果或抛出明确的异常",
                    )
                ],
                function=func,
            ))

        # 高复杂度函数增加额外的异常输入测试
        if func.complexity >= 3:
            cases.append(TestCase(
                id=f"unit_{func.name}_invalid_input",
                name=f"{func.name} - 异常输入",
                description=f"使用非法参数调用 {func.name}",
                test_type=TestType.UNIT,
                tags=["unit", func.module, "error"],
                priority="medium",
                steps=[
                    TestStep(
                        step_number=1,
                        action=f"调用 {func.name}，传入类型不匹配的参数",
                        expected_result="抛出 TypeError 或返回错误信息",
                    )
                ],
                function=func,
            ))

        return cases[:context.max_cases_per_function]

    def _fallback_generic_cases(
        self, context: GenerationContext, test_type: TestType
    ) -> list[TestCase]:
        """
        通用规则模板：生成 3 个基础用例
        
        适用于 E2E / Integration / Performance 等无专门解析器的类型：
          1. 功能验证 - 正常流程 (high)
          2. 边界条件测试 (medium)
          3. 异常处理测试 (medium)
        """
        return [
            TestCase(
                id=f"{test_type.value}_001",
                name="功能验证 - 正常流程",
                description="验证核心功能在正常条件下的表现",
                test_type=test_type,
                tags=["smoke"],
                priority="high",
                steps=[
                    TestStep(step_number=1, action="执行正常流程", expected_result="功能按预期工作")
                ],
            ),
            TestCase(
                id=f"{test_type.value}_002",
                name="边界条件测试",
                description="验证系统在边界条件下的表现",
                test_type=test_type,
                tags=["boundary"],
                priority="medium",
                steps=[
                    TestStep(step_number=1, action="输入边界值", expected_result="系统正确处理边界情况")
                ],
            ),
            TestCase(
                id=f"{test_type.value}_003",
                name="异常处理测试",
                description="验证系统对异常输入的处理",
                test_type=test_type,
                tags=["error"],
                priority="medium",
                steps=[
                    TestStep(step_number=1, action="输入异常数据", expected_result="系统返回友好的错误信息，不崩溃")
                ],
            ),
        ]
