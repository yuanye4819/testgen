"""
Python 源代码 AST 解析器
---------------------------
使用 Python 标准库 ast 模块遍历源代码，提取函数、方法和类定义。

核心能力:
  - 提取函数签名（参数、类型注解、默认值）
  - 提取类结构（方法列表、继承关系、装饰器）
  - 计算圈复杂度（用于判断测试深度）
  - 获取源码片段（ast.unparse）供 LLM 分析

限制:
  - 仅支持 Python 3.10+（依赖 ast.unparse）
  - 不做跨文件类型解析（import 的模块不会递归分析）
  - 跳过 __ 方法（魔术方法），减少无关用例
"""

import ast
from pathlib import Path
from typing import Any

from ..core.base import BaseParser
from ..core.models import (
    GenerationContext,
    FunctionDef,
    ClassDef,
    Parameter,
    InputSource,
    TestType,
)


class CodeParser(BaseParser):
    """
    基于 AST 解析 Python 源代码
    
    支持输入为单个 .py 文件或整个项目目录。
    目录模式下会递归扫描所有 .py 文件。
    
    自动跳过有语法错误的文件（打印警告，继续处理其余文件）。
    """

    def can_handle(self, context: GenerationContext) -> bool:
        return context.input_source == InputSource.SOURCE_CODE

    def parse(self, context: GenerationContext) -> GenerationContext:
        """
        扫描并解析 Python 源文件
        
        处理流程:
          1. 根据 raw_input 判断是文件还是目录
          2. 目录 → rglob("*.py") 递归扫描
          3. 逐个文件解析 AST，提取函数和类
          4. 如果未指定 test_types，自动设为 UNIT
        """
        functions: list[FunctionDef] = []
        classes: list[ClassDef] = []

        # 如果 raw_input 是目录，扫描所有 .py 文件
        src_path = Path(context.raw_input)
        if src_path.is_dir():
            py_files = list(src_path.rglob("*.py"))
            context.source_files = [str(f) for f in py_files]
        elif src_path.is_file():
            py_files = [src_path]
            context.source_files = [str(src_path)]
        else:
            raise ValueError(f"路径不存在: {context.raw_input}")

        for py_file in py_files:
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
                module_name = py_file.stem
                visitor = _ModuleVisitor(module_name, str(py_file))
                visitor.visit(tree)
                functions.extend(visitor.functions)
                classes.extend(visitor.classes)
            except SyntaxError as e:
                print(f"  [!] 跳过语法错误文件 {py_file}: {e}")
                continue

        context.functions = functions
        context.classes = classes
        if not context.test_types:
            context.test_types.append(TestType.UNIT)

        return context


class _ModuleVisitor(ast.NodeVisitor):
    """
    AST 遍历器 — 提取函数和类定义
    
    工作方式:
      visit_FunctionDef → _parse_function() → functions 列表
      visit_ClassDef    → 遍历 body 中的方法 → _parse_function() → methods 列表
    
    会自动跳过魔术方法（__xxx__），减少噪音。
    """

    def __init__(self, module: str, filepath: str = ""):
        self.module = module
        self.filepath = filepath
        self.functions: list[FunctionDef] = []
        self.classes: list[ClassDef] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        func = self._parse_function(node, self.module)
        self.functions.append(func)
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        func = self._parse_function(node, self.module, is_async=True)
        self.functions.append(func)
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        cls = ClassDef(
            name=node.name,
            module=self.module,
            docstring=ast.get_docstring(node) or "",
            base_classes=[self._name_str(b) for b in node.bases],
            decorators=[self._name_str(d) for d in node.decorator_list],
        )

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 跳过私有方法和魔术方法（可通过配置调整）
                if item.name.startswith("__"):
                    continue
                method = self._parse_function(item, self.module, parent_class=cls.name)
                cls.methods.append(method)

        self.classes.append(cls)
        return None

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        module: str,
        parent_class: str = "",
        is_async: bool = False,
    ) -> FunctionDef:
        """解析函数/方法"""
        params = []
        for arg in node.args.args:
            param_type = ""
            if arg.annotation:
                param_type = self._annotation_str(arg.annotation)
            params.append(Parameter(
                name=arg.arg,
                param_type="arg",
                required=True,
                schema={"type": param_type} if param_type else None,
            ))

        # 处理带默认值的参数
        defaults_offset = len(node.args.args) - len(node.args.defaults)
        for i, default in enumerate(node.args.defaults):
            idx = defaults_offset + i
            if idx < len(params):
                params[idx].required = False
                try:
                    params[idx].default = ast.literal_eval(default)
                except (ValueError, SyntaxError):
                    params[idx].default = ast.unparse(default)

        return_type = ""
        if node.returns:
            return_type = self._annotation_str(node.returns)

        decorators = [self._name_str(d) for d in node.decorator_list]

        # 简单圈复杂度估算
        complexity = self._estimate_complexity(node)

        full_name = f"{parent_class}.{node.name}" if parent_class else node.name

        return FunctionDef(
            name=full_name,
            module=module,
            docstring=ast.get_docstring(node) or "",
            parameters=params,
            return_type=return_type,
            source_code=self._get_source_snippet(node),
            decorators=decorators,
            complexity=complexity,
        )

    def _name_str(self, node: ast.expr) -> str:
        """
        将 AST 节点转换为名称字符串
        
        支持: Name(id) / Attribute(value.attr) / Call(func) 等嵌套结构。
        用于装饰器、基类列表的字符串化。
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._name_str(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):
            return self._name_str(node.func)
        return ast.unparse(node) if hasattr(ast, "unparse") else "..."

    def _annotation_str(self, node: ast.expr) -> str:
        """
        提取类型注解字符串
        
        例: int → "int" / list[str] → "list"（简化） / Optional[int] → "Optional"
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Subscript):
            base = self._annotation_str(node.value)
            return base
        if isinstance(node, ast.Constant):
            return str(node.value)
        return ast.unparse(node) if hasattr(ast, "unparse") else "Any"

    def _get_source_snippet(self, node: ast.AST) -> str:
        """获取函数源码片段（通过 ast.unparse 反编译），失败返回空字符串"""
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _estimate_complexity(self, node: ast.AST) -> int:
        """
        估算圈复杂度（Cyclomatic Complexity）
        
        基础值为 1，每遇到一个分支/循环节点 +1：
          - 条件: if / elif / except
          - 循环: for / while / async for
          - 布尔: and / or（每个额外条件 +1）
        
        返回值用于判断是否需要生成更多测试用例。
        """
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor,
                                  ast.ExceptHandler, ast.And, ast.Or)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity
