"""
OpenAPI / Swagger 解析器
---------------------------
解析 OpenAPI 3.x / Swagger 2.x 规范文件，将 paths 结构
提取为统一的 APIEndpoint 列表。

支持的格式: JSON (.json) 和 YAML (.yaml / .yml)

核心流程:
  1. _load_spec()    → 加载并反序列化规范文件
  2. _parse_endpoint() → 逐个端点解析参数、请求体、响应
  3. _parse_parameter() → 解析单个参数（含 schema 提取）
  
注意: Swagger 2.x 的 "body" 参数和 "consumes" 字段
会自适应转换为 OpenAPI 3.x 的 requestBody 结构。
"""

import json
import yaml
from pathlib import Path
from typing import Any

from ..core.base import BaseParser
from ..core.models import (
    GenerationContext,
    APIEndpoint,
    Parameter,
    HttpMethod,
    InputSource,
    TestType,
)


class OpenAPIParser(BaseParser):
    """
    解析 OpenAPI/Swagger 规范文件
    
    用法:
        parser = OpenAPIParser()
        context = parser.parse(context)  # context.api_endpoints 被填充
    """

    def __init__(self):
        self._spec: dict[str, Any] = {}

    def can_handle(self, context: GenerationContext) -> bool:
        return context.input_source == InputSource.OPENAPI

    def parse(self, context: GenerationContext) -> GenerationContext:
        spec_path = Path(context.raw_input)
        self._spec = self._load_spec(spec_path)

        if "paths" not in self._spec:
            raise ValueError("OpenAPI spec 中未找到 'paths' 定义")

        endpoints: list[APIEndpoint] = []

        for path, methods in self._spec["paths"].items():
            for method_name, operation in methods.items():
                if method_name.upper() not in HttpMethod.__members__:
                    continue

                endpoint = self._parse_endpoint(path, method_name.upper(), operation)
                endpoints.append(endpoint)

        context.api_endpoints = endpoints
        if not context.test_types:
            context.test_types.append(TestType.API)

        return context

    def _load_spec(self, path: Path) -> dict[str, Any]:
        """
        加载并解析 JSON/YAML 规范文件
        
        自动根据文件扩展名选择解析器。
        JSON: json.loads
        YAML: yaml.safe_load
        
        Raises:
            ValueError: 不支持的扩展名
        """
        content = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(content) or {}
        elif path.suffix == ".json":
            return json.loads(content)
        else:
            raise ValueError(f"不支持的文件格式: {path.suffix}，需要 .json / .yaml / .yml")

    def _parse_endpoint(
        self, path: str, method: str, operation: dict[str, Any]
    ) -> APIEndpoint:
        """
        解析单个 API 端点
        
        处理逻辑:
          1. 合并路径级 + 操作级参数（操作级覆盖路径级同名参数）
          2. 解析 requestBody（OpenAPI 3.x）或 body 参数（Swagger 2.x）
          3. 提取所有 HTTP 响应定义
        """
        parameters: list[Parameter] = []

        # 解析路径级参数（OpenAPI 3.x）
        for param in self._spec.get("paths", {}).get(path, {}).get("parameters", []):
            parameters.append(self._parse_parameter(param))

        # 解析操作级参数
        for param in operation.get("parameters", []):
            # 允许操作级参数覆盖路径级
            existing = [p for p in parameters if p.name == param.get("name")]
            if existing:
                parameters.remove(existing[0])
            parameters.append(self._parse_parameter(param))

        # 解析 requestBody (OpenAPI 3.x)
        request_body = None
        if "requestBody" in operation:
            request_body = self._parse_request_body(operation["requestBody"])
        elif "consumes" in operation:
            # Swagger 2.x
            for param in operation.get("parameters", []):
                if param.get("in") == "body":
                    request_body = param.get("schema", {})
                    break

        # 解析响应
        responses: dict[str, Any] = {}
        for status, resp in operation.get("responses", {}).items():
            responses[status] = {
                "description": resp.get("description", ""),
                "content": self._extract_response_schema(resp),
            }

        return APIEndpoint(
            path=path,
            method=HttpMethod[method],
            summary=operation.get("summary", ""),
            description=operation.get("description", operation.get("summary", "")),
            parameters=parameters,
            request_body=request_body,
            responses=responses,
            tags=operation.get("tags", []),
        )

    def _parse_parameter(self, param: dict[str, Any]) -> Parameter:
        """
        解析单个参数定义
        
        提取 name, in（参数位置）, required, description, example, schema。
        example 优先取 param.example，回退到 schema.example。
        """
        schema = param.get("schema", {})
        return Parameter(
            name=param.get("name", ""),
            param_type=param.get("in", "query"),
            required=param.get("required", False),
            description=param.get("description", ""),
            example=param.get("example") or schema.get("example"),
            schema=schema,
        )

    def _parse_request_body(self, request_body: dict[str, Any]) -> dict | None:
        """解析请求体，返回 application/json 的 schema"""
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        return schema if schema else None

    def _extract_response_schema(self, response: dict[str, Any]) -> dict | None:
        """提取响应中的 application/json schema"""
        content = response.get("content", {})
        json_content = content.get("application/json", {})
        return json_content.get("schema")
