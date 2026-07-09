"""
自然语言解析器
----------------
处理用户以自然语言描述的功能需求。

与 OpenAPI/Code 解析器不同，此解析器不做结构化提取，
而是：
  1. 将原始文本原样存入 context.natural_lang_desc
  2. 通过关键词启发式推测用户可能想要的测试类型

真正的"理解"由 LLM 生成器完成——此解析器只是将文本
送达到正确的位置。
"""

from pathlib import Path

from ..core.base import BaseParser
from ..core.models import GenerationContext, InputSource


class NaturalLangParser(BaseParser):
    """
    自然语言输入处理器
    
    支持的输入形式:
      - 直接文本: "测试用户登录功能，包括正常登录和密码错误"
      - 文件路径: 指向 .txt / .md / .docx / .pdf 文件，自动提取文本
    
    Keyword 映射（启发式）:
      api / 接口 / http / endpoint     → TestType.API
      函数 / 方法 / 单元测试 / function → TestType.UNIT
      页面 / ui / 端到端 / e2e / 浏览器 → TestType.E2E
    """

    def can_handle(self, context: GenerationContext) -> bool:
        return context.input_source == InputSource.NATURAL_LANG

    def parse(self, context: GenerationContext) -> GenerationContext:
        raw = context.raw_input.strip()

        if not raw:
            raise ValueError("自然语言输入不能为空")

        # 如果输入是文件路径，根据扩展名读取内容
        p = Path(raw)
        if p.exists() and p.is_file():
            suffix = p.suffix.lower()
            if suffix == ".docx":
                raw = self._read_docx(p)
            elif suffix == ".pdf":
                raw = self._read_pdf(p)
            else:
                raw = p.read_text(encoding="utf-8")

        context.natural_lang_desc = raw

        # 启发式：根据关键词推测测试类型
        lower = raw.lower()
        from ..core.models import TestType
        if any(kw in lower for kw in ("api", "接口", "请求", "http", "endpoint")):
            if TestType.API not in context.test_types:
                context.test_types.append(TestType.API)
        if any(kw in lower for kw in ("函数", "方法", "单元测试", "function", "unit test")):
            if TestType.UNIT not in context.test_types:
                context.test_types.append(TestType.UNIT)
        if any(kw in lower for kw in ("页面", "ui", "端到端", "e2e", "浏览器")):
            if TestType.E2E not in context.test_types:
                context.test_types.append(TestType.E2E)

        return context

    def _read_docx(self, filepath: Path) -> str:
        """从 .docx 文件中提取纯文本"""
        try:
            from docx import Document
            doc = Document(str(filepath))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except ImportError:
            raise ImportError("请安装 python-docx: pip install python-docx")
        except Exception as e:
            raise ValueError(f"无法解析 .docx 文件: {e}")

    def _read_pdf(self, filepath: Path) -> str:
        """从 .pdf 文件中提取纯文本"""
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(str(filepath)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n\n".join(text_parts)
        except ImportError:
            raise ImportError("请安装 pdfplumber: pip install pdfplumber")
        except Exception as e:
            raise ValueError(f"无法解析 .pdf 文件: {e}")
