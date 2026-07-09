"""
LLM 客户端
-----------
封装 OpenAI 兼容 API 调用，屏蔽底层细节。

特性:
  - 支持任意 OpenAI 兼容服务（OpenAI / Ollama / DeepSeek / vLLM 等）
  - 延迟初始化: 仅在首次调用时创建连接
  - 双模式: chat() 返回原始文本 / chat_json() 强制返回 JSON
  - 通过环境变量配置:
      OPENAI_API_KEY  - API 密钥（必需）
      OPENAI_BASE_URL - 自定义端点（可选，默认 OpenAI 官方）
"""

import json
import os
from typing import Optional

from ..core.models import GenerationContext


class LLMClient:
    """OpenAI 兼容的 LLM 客户端"""

    def __init__(self):
        self._client = None

    def _ensure_client(self, context: GenerationContext):
        """延迟初始化 OpenAI 客户端"""
        if self._client is not None:
            return

        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", None)

        if not api_key:
            raise ValueError(
                "请设置环境变量 OPENAI_API_KEY。\n"
                "可使用本地模型: export OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama"
            )

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("请安装 openai 包: pip install openai")

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url

        self._client = OpenAI(**kwargs)

    def chat(
        self,
        context: GenerationContext,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> str:
        """发送聊天消息并返回响应文本"""
        self._ensure_client(context)

        temp = temperature if temperature is not None else context.llm_temperature

        response = self._client.chat.completions.create(
            model=context.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
        )

        return response.choices[0].message.content or ""

    def chat_json(
        self,
        context: GenerationContext,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> dict:
        """发送聊天消息并返回解析后的 JSON"""
        self._ensure_client(context)

        temp = temperature if temperature is not None else context.llm_temperature

        response = self._client.chat.completions.create(
            model=context.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON
            import re
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                return json.loads(match.group())
            return {"error": "JSON 解析失败", "raw": content}
