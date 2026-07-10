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
            elif test_type == TestType.GUI:
                suites.append(self._generate_gui_rules(context))
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
                print(f"  [!] LLM 生成失败 ({endpoint.method.value} {endpoint.path}): {e}")
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
                print(f"  [!] LLM 生成失败 ({func.name}): {e}")
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
            print(f"  [!] LLM 生成失败: {e}")
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
                priority=rc.get("priority", "P2"),
                preconditions=rc.get("preconditions", ""),
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

    def _generate_gui_rules(self, context: GenerationContext) -> TestSuite:
        """规则模式：生成 GUI 测试用例"""
        return TestSuite(
            name="GUI_Tests",
            description="基于规则生成的 GUI 测试用例",
            test_cases=self._fallback_gui_cases(context),
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
            priority="P0",
            preconditions="服务正常运行",
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
                priority="P0",
                preconditions="",
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
                priority="P2",
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
            priority="P0",
            preconditions="所有依赖可用",
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
                priority="P2",
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
                priority="P2",
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


    def _fallback_gui_cases(self, context: GenerationContext) -> list[TestCase]:
        """GUI 测试专用规则模板"""
        return [
            TestCase(
                id="gui_001", name="界面元素完整性验证",
                description="验证页面所有必要UI元素（输入框、按钮、标签、图标）是否存在且可见",
                test_type=TestType.GUI, tags=["gui", "smoke"], priority="P0",
                preconditions="系统正常启动，进入目标页面",
                steps=[TestStep(step_number=1, action="逐一检查页面UI元素", expected_result="所有元素存在且可见")],
                expected_result="页面元素完整，无缺失，无重叠",
                module="界面验证", sub_feature="元素检查",
            ),
            TestCase(
                id="gui_002", name="界面布局验证-不同分辨率",
                description="验证在不同分辨率（1366x768、1920x1080、2560x1440）下页面布局是否正常",
                test_type=TestType.GUI, tags=["gui", "layout"], priority="P1",
                preconditions="准备不同分辨率的测试环境",
                steps=[TestStep(step_number=1, action="切换分辨率并截图对比", expected_result="页面布局自适应，无错位、遮挡、溢出")],
                expected_result="各分辨率下布局正常，元素对齐正确",
                module="界面验证", sub_feature="布局适配",
            ),
            TestCase(
                id="gui_003", name="文本内容核对",
                description="验证页面所有文本内容（标题、提示、按钮文字、错误信息）是否与需求文档一致",
                test_type=TestType.GUI, tags=["gui", "text"], priority="P1",
                preconditions="准备需求文档/UI设计稿",
                steps=[TestStep(step_number=1, action="逐项核对页面文字与需求文档", expected_result="所有文本与需求一致，无错别字，无乱码")],
                expected_result="文字内容准确，无错别字",
                module="界面验证", sub_feature="文本核对",
            ),
            TestCase(
                id="gui_004", name="按钮交互验证",
                description="验证所有按钮的点击、悬停、禁用三种状态的视觉反馈",
                test_type=TestType.GUI, tags=["gui", "interaction"], priority="P1",
                preconditions="进入包含按钮的页面",
                steps=[
                    TestStep(step_number=1, action="鼠标悬停在按钮上", expected_result="按钮显示hover样式（颜色变化或阴影）"),
                    TestStep(step_number=2, action="点击按钮", expected_result="按钮有点击反馈（按下效果），触发对应功能"),
                    TestStep(step_number=3, action="查看禁用按钮", expected_result="禁用按钮呈灰色，不可点击"),
                ],
                expected_result="按钮三种状态视觉反馈正确",
                module="交互验证", sub_feature="按钮状态",
            ),
            TestCase(
                id="gui_005", name="输入框交互验证",
                description="验证输入框的获取焦点、输入、失焦、错误提示的视觉表现",
                test_type=TestType.GUI, tags=["gui", "interaction"], priority="P1",
                preconditions="进入包含输入框的页面",
                steps=[
                    TestStep(step_number=1, action="点击输入框获取焦点", expected_result="输入框高亮，光标出现，显示边框变色"),
                    TestStep(step_number=2, action="输入文本内容", expected_result="文字正常显示，placeholder消失"),
                    TestStep(step_number=3, action="点击其他区域失焦", expected_result="输入框恢复默认样式"),
                    TestStep(step_number=4, action="输入非法内容并提交", expected_result="输入框变红，显示错误提示文字"),
                ],
                expected_result="输入框四种状态视觉表现正确",
                module="交互验证", sub_feature="输入框状态",
            ),
            TestCase(
                id="gui_006", name="弹窗/对话框验证",
                description="验证弹窗的弹出、关闭、遮罩层是否正常",
                test_type=TestType.GUI, tags=["gui", "dialog"], priority="P2",
                preconditions="触发弹窗的条件已满足",
                steps=[
                    TestStep(step_number=1, action="触发弹窗弹出", expected_result="弹窗居中显示，背景有半透明遮罩，弹窗外区域不可操作"),
                    TestStep(step_number=2, action="点击关闭按钮或遮罩", expected_result="弹窗关闭，页面恢复正常"),
                ],
                expected_result="弹窗正常弹出和关闭，遮罩有效",
                module="交互验证", sub_feature="弹窗",
            ),
            TestCase(
                id="gui_007", name="列表/表格验证",
                description="验证列表或表格的列头、数据行、分页、排序图标的显示",
                test_type=TestType.GUI, tags=["gui", "table"], priority="P2",
                preconditions="列表页面已加载数据",
                steps=[
                    TestStep(step_number=1, action="查看表头样式", expected_result="表头背景色、字体加粗，与数据行区分明显"),
                    TestStep(step_number=2, action="查看数据行交替色", expected_result="奇偶行背景色交替，提高可读性"),
                    TestStep(step_number=3, action="鼠标悬停数据行", expected_result="当前行高亮显示"),
                ],
                expected_result="列表样式规范，交互反馈正确",
                module="界面验证", sub_feature="列表样式",
            ),
            TestCase(
                id="gui_008", name="图标与图片验证",
                description="验证页面图标和图片是否正常加载、尺寸正确、无拉伸变形",
                test_type=TestType.GUI, tags=["gui", "image"], priority="P2",
                preconditions="页面包含图标或图片元素",
                steps=[TestStep(step_number=1, action="检查所有图标和图片", expected_result="全部正常加载，无裂图，尺寸比例正确")],
                expected_result="图标图片显示正常",
                module="界面验证", sub_feature="图标图片",
            ),
        ]

    def _fallback_generic_cases(
        self, context: GenerationContext, test_type: TestType
    ) -> list[TestCase]:
        """通用规则模板：有 URL 页面数据则生成针对性用例，否则生成骨架"""
        
        # ── URL 模式：基于页面元素生成 ──────────────────
        if context.page_elements:
            return self._generate_url_cases(context, test_type)
        
        # ── 通用骨架 ─────────────────────────────────────
        return [
            TestCase(
                id=f"{test_type.value}_001",
                name="功能验证 - 正常流程",
                description="验证核心功能在正常条件下的表现",
                test_type=test_type,
                tags=["smoke"],
                priority="P0",
                steps=[TestStep(step_number=1, action="执行正常流程", expected_result="功能按预期工作")],
            ),
            TestCase(
                id=f"{test_type.value}_002",
                name="边界条件测试",
                description="验证系统在边界条件下的表现",
                test_type=test_type,
                tags=["boundary"],
                priority="P2",
                steps=[TestStep(step_number=1, action="输入边界值", expected_result="系统正确处理边界情况")],
            ),
            TestCase(
                id=f"{test_type.value}_003",
                name="异常处理测试",
                description="验证系统对异常输入的处理",
                test_type=test_type,
                tags=["error"],
                priority="P2",
                steps=[TestStep(step_number=1, action="输入异常数据", expected_result="系统返回友好的错误信息，不崩溃")],
            ),
        ]

    def _generate_url_cases(self, context, test_type) -> list[TestCase]:
        """根据抓取的页面元素生成针对性测试用例"""
        pe = context.page_elements
        title = context.page_title or "页面"
        cases = []
        idx = 0

        # 页面加载验证
        idx += 1
        cases.append(TestCase(
            id=f"{test_type.value}_{idx:03d}",
            name=f"{title} - 页面加载验证",
            description=f"验证 {title} 页面能正常加载，页面元素完整显示",
            test_type=test_type, tags=["smoke", "e2e"], priority="P0",
            preconditions="网络正常，服务可用",
            steps=[TestStep(step_number=1, action=f"访问页面 {title}", expected_result="页面正常加载，HTTP 200，页面元素完整渲染")],
            expected_result="页面成功加载，所有关键元素可见",
        ))

        # 表单测试
        for i, form in enumerate(pe.get("forms", [])):
            idx += 1
            method = form.get("method", "GET")
            fields = form.get("inputs", [])
            field_desc = "、".join(f"{f['name']}({f['type']})" for f in fields if f["name"])
            required_fields = [f["name"] for f in fields if f.get("required")]
            cases.append(TestCase(
                id=f"{test_type.value}_{idx:03d}",
                name=f"{title} - 表单{i+1}正常提交",
                description=f"使用合法数据提交 {method} 表单，字段: {field_desc}",
                test_type=test_type, tags=["smoke", "form"], priority="P0",
                preconditions="表单字段可正常交互",
                steps=[TestStep(step_number=1, action=f"填写所有必填字段并点击提交", expected_result="表单成功提交，跳转或显示成功提示")],
                expected_result="表单提交成功，无错误提示",
            ))
            if required_fields:
                idx += 1
                cases.append(TestCase(
                    id=f"{test_type.value}_{idx:03d}",
                    name=f"{title} - 表单{i+1}必填字段校验",
                    description=f"不填必填字段（{', '.join(required_fields[:3])}）提交表单",
                    test_type=test_type, tags=["validation", "form"], priority="P1",
                    preconditions="表单可访问",
                    steps=[TestStep(step_number=1, action="清空必填字段，直接点击提交", expected_result="显示必填字段校验提示，表单不提交")],
                    expected_result="触发前端校验，阻止空表单提交",
                ))

        # 按钮测试
        buttons = pe.get("buttons", [])
        for i, btn in enumerate(buttons[:5]):
            idx += 1
            cases.append(TestCase(
                id=f"{test_type.value}_{idx:03d}",
                name=f"{title} - 按钮「{btn}」可点击",
                description=f"验证按钮「{btn}」存在且可点击",
                test_type=test_type, tags=["ui", "button"], priority="P1",
                steps=[TestStep(step_number=1, action=f"点击「{btn}」按钮", expected_result="按钮响应，触发对应操作或跳转")],
                expected_result="按钮可正常点击，无JS报错",
            ))

        # 链接测试
        links = pe.get("links", [])
        for i, link in enumerate(links[:5]):
            idx += 1
            cases.append(TestCase(
                id=f"{test_type.value}_{idx:03d}",
                name=f"{title} - 链接「{link['text']}」可跳转",
                description=f"验证链接「{link['text']}」({link['href'][:80]}) 可正常跳转",
                test_type=test_type, tags=["ui", "link"], priority="P2",
                steps=[TestStep(step_number=1, action=f"点击链接「{link['text']}」", expected_result="跳转到目标页面，HTTP 200")],
                expected_result="链接正常跳转，目标页面可访问",
            ))

        return cases[:15]
