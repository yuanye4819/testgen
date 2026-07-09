"""
基础抽象类定义
----------------
定义了系统中所有核心接口规范，确保解析器、生成器、输出适配器
可以独立开发和替换。

设计原则：
  - 依赖倒置：高层模块（Orchestrator）只依赖这些抽象接口
  - 单一职责：每个抽象类只定义一类行为
  - 开闭原则：新增功能只需实现接口，无需修改已有代码
"""

from abc import ABC, abstractmethod
from typing import Any

from .models import (
    GenerationContext,
    TestSuite,
    APIEndpoint,
    FunctionDef,
    ClassDef,
)


class BaseParser(ABC):
    """
    输入解析器基类
    
    所有输入解析器必须实现此接口。解析器负责将原始输入（文件、文本）
    转换为结构化的数据模型，填充到 GenerationContext 中。
    
    使用方式:
        parser = OpenAPIParser()
        if parser.can_handle(context):
            context = parser.parse(context)
    """

    @abstractmethod
    def parse(self, context: GenerationContext) -> GenerationContext:
        """
        解析输入，填充 context 中的对应字段
        
        Args:
            context: 包含 raw_input 等原始数据的上下文对象
            
        Returns:
            更新后的 GenerationContext（api_endpoints / functions / classes 等已填充）
            
        Raises:
            ValueError: 输入格式不正确或文件不存在
        """
        ...

    @abstractmethod
    def can_handle(self, context: GenerationContext) -> bool:
        """
        判断当前解析器是否能处理该输入
        
        Args:
            context: 包含 input_source 的上下文
            
        Returns:
            True 表示可以处理，False 表示应尝试其他解析器
        """
        ...


class BaseGenerator(ABC):
    """
    测试用例生成器基类
    
    生成器从解析后的上下文生成测试用例套件。支持两种策略：
      - LLM 模式：调用大模型智能生成
      - 规则模式：基于预设模板回退生成
    """

    @abstractmethod
    def generate(self, context: GenerationContext) -> list[TestSuite]:
        """
        根据上下文生成测试用例套件
        
        Args:
            context: 已解析完毕的生成上下文
            
        Returns:
            测试套件列表，每个套件包含若干测试用例
        """
        ...


class BaseOutputAdapter(ABC):
    """
    输出适配器基类
    
    将内存中的测试套件写入为具体格式的文件（.py / .json / .xlsx 等）。
    每个适配器对应一种输出格式。
    """

    @abstractmethod
    def write(self, suites: list[TestSuite], context: GenerationContext) -> list[str]:
        """
        将测试套件写入目标格式
        
        Args:
            suites:   待输出的测试套件列表
            context:  包含 output_dir 等输出配置的上下文
            
        Returns:
            实际生成的文件路径列表，用于后续摘要展示
        """
        ...

    @abstractmethod
    def format_name(self) -> str:
        """
        返回适配器的格式名称标识
        
        Returns:
            格式名，如 "pytest", "json", "excel"
        """
        ...
