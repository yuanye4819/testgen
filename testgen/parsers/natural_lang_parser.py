"""
自然语言 / URL 解析器
------------------------
处理用户以自然语言描述的功能需求，或通过网页 URL 自动分析页面。

URL 模式:
  输入 URL → 抓取页面 → 提取标题、表单、按钮、链接
  → 转换为结构化测试需求描述 → 交给生成器

文本模式:
  自然语言文本原样存入 context.natural_lang_desc
"""

import re
from pathlib import Path

from ..core.base import BaseParser
from ..core.models import GenerationContext, InputSource


class NaturalLangParser(BaseParser):
    """
    输入处理器 — 支持自然语言文本、文件、URL 三种形式
    
    文本: "测试用户登录功能，包括正常登录和密码错误"
    文件: .txt / .md / .docx / .pdf
    URL:  https://example.com/login
    """

    def can_handle(self, context: GenerationContext) -> bool:
        return context.input_source in (InputSource.NATURAL_LANG, InputSource.URL)

    def parse(self, context: GenerationContext) -> GenerationContext:
        raw = context.raw_input.strip()

        if not raw:
            raise ValueError("输入不能为空")

        # ── URL 模式 ──────────────────────────────
        if context.input_source == InputSource.URL or self._is_url(raw):
            context.input_source = InputSource.URL
            parsed = self._fetch_and_parse_url(raw)
            context.natural_lang_desc = parsed["desc"]
            context.page_title = parsed["title"]
            context.page_elements = parsed["elements"]
            return context

        # ── 文件模式 ──────────────────────────────
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

        # 启发式关键词 → 测试类型
        lower = raw.lower()
        from ..core.models import TestType
        if any(kw in lower for kw in ("api", "接口", "请求", "http", "endpoint")):
            if TestType.API not in context.test_types:
                context.test_types.append(TestType.API)
        if any(kw in lower for kw in ("函数", "方法", "单元测试", "function", "unit test")):
            if TestType.UNIT not in context.test_types:
                context.test_types.append(TestType.UNIT)
        if any(kw in lower for kw in ("页面", "ui", "端到端", "e2e", "浏览器", "表单", "按钮")):
            if TestType.E2E not in context.test_types:
                context.test_types.append(TestType.E2E)

        return context

    def _is_url(self, text: str) -> bool:
        """检测输入是否为 URL"""
        return bool(re.match(r'^https?://', text.strip()))

    def _fetch_and_parse_url(self, url: str) -> dict:
        """抓取网页并提取结构化信息"""
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError("请安装依赖: pip install requests beautifulsoup4")

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(url, timeout=30, headers=headers)
            resp.raise_for_status()
        except Exception as e:
            raise ValueError(f"无法访问网页: {e}")

        # 使用 resp.content 让 BeautifulSoup 自动检测编码
        soup = BeautifulSoup(resp.content, "html.parser")

        # 提取页面标题
        title = soup.title.string.strip() if soup.title else "未命名页面"

        elements: dict[str, list] = {
            "forms": [],
            "buttons": [],
            "inputs": [],
            "links": [],
            "headings": [],
        }

        # 提取表单
        for form in soup.find_all("form"):
            form_info = {
                "action": form.get("action", ""),
                "method": form.get("method", "GET"),
                "inputs": [],
            }
            for inp in form.find_all(["input", "select", "textarea"]):
                form_info["inputs"].append({
                    "name": inp.get("name", ""),
                    "type": inp.get("type", inp.name),
                    "placeholder": inp.get("placeholder", ""),
                    "required": inp.has_attr("required"),
                })
            elements["forms"].append(form_info)

        # 提取按钮
        for btn in soup.find_all(["button", "input[type=submit]", "input[type=button]"]):
            text = btn.get_text(strip=True) or btn.get("value", "")
            if text:
                elements["buttons"].append(text)

        # 提取独立输入框
        for inp in soup.find_all("input"):
            if inp.get("name") and inp.get("type") not in ("submit", "button", "hidden"):
                elements["inputs"].append({
                    "name": inp.get("name", ""),
                    "type": inp.get("type", "text"),
                    "placeholder": inp.get("placeholder", ""),
                })

        # 提取关键链接
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if text and not href.startswith("#") and not href.startswith("javascript"):
                elements["links"].append({"text": text[:60], "href": href[:120]})

        # 提取标题
        for h in soup.find_all(["h1", "h2", "h3"]):
            text = h.get_text(strip=True)
            if text:
                elements["headings"].append(text)

        # 构建自然语言描述
        desc_parts = [f"网页标题: {title}"]
        desc_parts.append(f"URL: {url}")

        if elements["headings"]:
            desc_parts.append(f"页面标题: {', '.join(elements['headings'][:5])}")

        if elements["forms"]:
            for i, form in enumerate(elements["forms"]):
                method = form["method"]
                action = form["action"] or "(当前页)"
                inputs_desc = ", ".join(
                    f"{inp['name']}({inp['type']})" + ("[必填]" if inp["required"] else "")
                    for inp in form["inputs"] if inp["name"]
                )
                desc_parts.append(f"表单{i+1}: {method} {action}, 字段: {inputs_desc}")

        if elements["buttons"]:
            desc_parts.append(f"操作按钮: {', '.join(elements['buttons'][:10])}")

        if elements["links"]:
            link_texts = [l["text"] for l in elements["links"][:10]]
            desc_parts.append(f"页面链接: {', '.join(link_texts)}")

        desc = "\n".join(desc_parts)
        desc += "\n\n请根据以上页面结构生成功能测试和端到端测试用例，覆盖表单提交、按钮点击、链接跳转等场景。"

        return {"title": title, "elements": elements, "desc": desc}

    def _read_docx(self, filepath: Path) -> str:
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
