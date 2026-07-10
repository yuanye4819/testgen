"""
测试用例数据模型
定义了系统中所有核心数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class TestType(Enum):
    """测试类型枚举"""
    API = "api"
    UNIT = "unit"
    E2E = "e2e"
    INTEGRATION = "integration"
    PERFORMANCE = "performance"
    FUNCTIONAL = "functional"


class HttpMethod(Enum):
    """HTTP 方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class InputSource(Enum):
    """输入来源枚举"""
    OPENAPI = "openapi"
    SOURCE_CODE = "source_code"
    NATURAL_LANG = "natural_lang"
    URL = "url"


class OutputFormat(Enum):
    """输出格式枚举"""
    PYTEST = "pytest"
    JSON = "json"
    YAML = "yaml"
    EXCEL = "excel"
    CSV = "csv"


@dataclass
class Parameter:
    """
    测试参数定义
    
    用于描述 API 请求参数或函数参数的结构。
    当用于 API 时，param_type 表示参数位置（query/path/header/body/form）；
    当用于函数时，param_type 固定为 "arg"。
    """
    name: str                     # 参数名称
    param_type: str               # query | path | header | body | form | arg
    required: bool = False        # 是否必填
    default: Optional[Any] = None # 默认值
    description: str = ""         # 参数描述（来自 OpenAPI 或 docstring）
    example: Optional[Any] = None # 示例值
    schema: Optional[dict] = None # JSON Schema 类型定义


@dataclass
class APIEndpoint:
    """
    API 端点定义
    
    从 OpenAPI/Swagger 规范中解析出的单个 API 端点完整描述，
    包含路径、HTTP 方法、参数、请求体和响应定义。
    这是生成 API 测试用例的核心输入。
    """
    path: str                             # 端点路径，如 /users/{userId}
    method: HttpMethod                     # HTTP 方法
    summary: str = ""                      # 简短摘要（OpenAPI summary）
    description: str = ""                  # 详细描述（OpenAPI description）
    parameters: list[Parameter] = field(default_factory=list)  # 请求参数列表
    request_body: Optional[dict] = None    # 请求体 JSON Schema
    responses: dict[str, Any] = field(default_factory=dict)    # 响应定义 {status: schema}
    tags: list[str] = field(default_factory=list)              # OpenAPI tags 分类


@dataclass
class FunctionDef:
    """
    函数/方法定义
    
    从 Python 源代码 AST 中提取的函数完整信息，
    包括签名、docstring、圈复杂度等。用于生成单元测试用例。
    """
    name: str                           # 函数全名（含类名前缀，如 MyClass.method）
    module: str = ""                    # 所属模块名（文件名）
    docstring: str = ""                 # 函数文档字符串
    parameters: list[Parameter] = field(default_factory=list)  # 参数列表
    return_type: str = ""               # 返回类型注解
    source_code: str = ""               # 函数源码片段（ast.unparse）
    decorators: list[str] = field(default_factory=list)        # 装饰器列表
    complexity: int = 0                 # 圈复杂度（用于决定测试用例深度）


@dataclass
class ClassDef:
    """
    类定义
    
    从 Python 源代码 AST 中提取的类结构，包含方法列表和继承关系。
    用于生成面向类的测试套件（setUp/tearDown）。
    """
    name: str                                # 类名
    module: str = ""                         # 所属模块名
    docstring: str = ""                      # 类文档字符串
    methods: list[FunctionDef] = field(default_factory=list)   # 公共方法列表（不含 __ 方法）
    base_classes: list[str] = field(default_factory=list)      # 父类名称列表
    decorators: list[str] = field(default_factory=list)        # 类装饰器


@dataclass
class TestStep:
    """
    测试步骤
    
    一个测试用例由一个或多个有序步骤组成，
    每个步骤描述一个操作动作和对应的预期结果。
    """
    step_number: int               # 步骤序号（从 1 开始）
    action: str                    # 操作描述（如 "发送 POST 请求到 /users"）
    expected_result: str           # 预期结果（如 "返回 HTTP 201，用户创建成功"）
    data: Optional[dict] = None    # 步骤需要的测试数据
    assertions: list[str] = field(default_factory=list)  # 具体断言列表


@dataclass
class TestCase:
    """
    单个测试用例
    
    测试用例是生成系统的最小输出单元，包含完整的前置条件、
    测试步骤和期望结果。兼容 API 测试和单元测试两种场景。
    
    优先级: P0（核心必测）| P1（重要）| P2（一般）| P3（低优）
    """
    id: str                                      # 唯一标识（如 api_GET__users_ok）
    name: str                                    # 用例名称
    description: str = ""                        # 详细描述
    test_type: TestType = TestType.API           # 测试类型
    tags: list[str] = field(default_factory=list)  # 标签（smoke, regression 等）
    priority: str = "P2"                         # 优先级: P0 | P1 | P2 | P3
    preconditions: str = ""                      # 前置条件
    steps: list[TestStep] = field(default_factory=list)     # 测试步骤
    expected_result: str = ""                    # 整体预期结果
    module: str = ""                             # 测试模块（模板字段）
    sub_feature: str = ""                        # 子功能（模板字段）
    system_name: str = ""                        # 所属系统（模板字段）
    
    # API 测试特有字段
    endpoint: Optional[APIEndpoint] = None       # 关联的 API 端点（回填引用）
    
    # 单元测试特有字段
    function: Optional[FunctionDef] = None       # 关联的函数定义（回填引用）
    
    # 期望结果
    expected_status: int = 200                   # 期望 HTTP 状态码
    expected_response: Optional[dict] = None     # 期望的响应体结构
    expected_error: Optional[str] = None         # 期望的错误信息
    
    # 扩展元数据
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestSuite:
    """
    测试套件
    
    一组相关测试用例的集合，可以包含 setup/teardown 代码。
    通常每个 API 端点或每个函数生成一个 suite。
    """
    name: str                                     # 套件名称
    description: str = ""                          # 套件描述
    test_cases: list[TestCase] = field(default_factory=list)  # 包含的测试用例
    setup_code: str = ""                           # 前置代码（如 fixture 准备）
    teardown_code: str = ""                        # 后置代码（如资源清理）
    metadata: dict[str, Any] = field(default_factory=dict)   # 扩展元数据

    @property
    def total_cases(self) -> int:
        """测试用例总数"""
        return len(self.test_cases)

    @property
    def by_priority(self) -> dict[str, list[TestCase]]:
        """按优先级分组，返回 {priority: [TestCase, ...]}"""
        result: dict[str, list[TestCase]] = {}
        for tc in self.test_cases:
            result.setdefault(tc.priority, []).append(tc)
        return result


@dataclass
class GenerationContext:
    """
    生成上下文 — 贯穿整个生成流程的统一数据载体
    
    所有模块通过此上下文交换数据，避免全局状态：
      - 解析器负责 写入 解析结果
      - 生成器负责 读取 解析结果并 写入 测试套件
      - 输出适配器负责 读取 测试套件并写入文件
    
    每个字段用注释标明所属阶段和读写权限。
    """
    # ── 输入阶段配置（CLI → 解析器）────────────────
    input_source: InputSource                      # 输入来源类型
    output_format: OutputFormat                    # 期望输出格式
    test_types: list[TestType] = field(default_factory=list)  # 要生成的测试类型
    raw_input: str = ""                            # 原始输入路径或文本
    source_files: list[str] = field(default_factory=list)     # 扫描到的源文件列表
    
    # ── 解析阶段产出（解析器 → 生成器）────────────────
    api_endpoints: list[APIEndpoint] = field(default_factory=list)   # OpenAPI 解析结果
    functions: list[FunctionDef] = field(default_factory=list)        # AST 解析的函数
    classes: list[ClassDef] = field(default_factory=list)             # AST 解析的类
    natural_lang_desc: str = ""                                      # 自然语言描述原文
    page_title: str = ""                                             # 网页标题（URL 模式）
    page_elements: dict[str, Any] = field(default_factory=dict)      # 页面元素（URL 模式）
    
    # ── 生成阶段配置（CLI → 生成器）──────────────────
    llm_enabled: bool = True                       # 是否启用 LLM（False 则用规则模板）
    llm_model: str = "gpt-4"                       # LLM 模型名（兼容 OpenAI API）
    llm_temperature: float = 0.3                   # LLM 温度（越低越确定）
    max_cases_per_endpoint: int = 5                # 每个 API 端点最大生成用例数
    max_cases_per_function: int = 3                # 每个函数最大生成用例数
    
    # ── 输出阶段配置（CLI → 输出适配器）─────────────
    output_dir: str = "./output"                   # 输出目录
    base_url: str = "http://localhost:8000"         # API 基础 URL
    
    # ── 扩展元数据 ────────────────────────────────
    metadata: dict[str, Any] = field(default_factory=dict)
