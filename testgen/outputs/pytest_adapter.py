"""
Pytest Output Adapter
Generates executable pytest test files from TestSuite objects.

Output structure:
  {output_dir}/pytest/
    conftest.py            # Shared fixtures (API client, base_url)
    {suite_name}_test.py   # One test file per suite

The conftest.py file is auto-generated on first run and provides:
  - base_url fixture:   Configurable base URL
  - api_client fixture: requests.Session-based HTTP client
"""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment

from ..core.base import BaseOutputAdapter
from ..core.models import GenerationContext, TestSuite, TestType, TestCase

PYTEST_TEMPLATE = '''# -*- coding: utf-8 -*-
"""
{{ suite.name }}
{{ suite.description }}
Generated at: {{ generation_time }}
Source: TestGen v{{ version }}
"""
import pytest
{% if suite.setup_code %}

# Setup
{{ suite.setup_code }}
{% endif %}

{% for case in suite.test_cases %}
# -----------------------------------------------------------------
# {{ case.name }}
# {{ case.description }}
# Priority: {{ case.priority }}  Tags: {{ case.tags | join(", ") }}
# -----------------------------------------------------------------
{% if case.preconditions %}
# Preconditions:
{% for p in case.preconditions %}
#   - {{ p }}
{% endfor %}
{% endif %}

{% if case.steps %}
{% for step in case.steps %}
def test_{{ case.id | replace("-", "_") | replace(".", "_") }}_step{{ step.step_number }}():
    """{{ step.action }}"""
    # Expected: {{ step.expected_result }}
{% for assertion in step.assertions %}
    # Assertion: {{ assertion }}
{% endfor %}
    # TODO: Implement test logic
    pass

{% endfor %}
{% else %}
def test_{{ case.id | replace("-", "_") | replace(".", "_") }}():
    """{{ case.description or case.name }}"""
    # TODO: Implement test logic
    pass

{% endif %}
{% endfor %}

{% if suite.teardown_code %}
# Teardown
{{ suite.teardown_code }}
{% endif %}
'''


class PytestAdapter(BaseOutputAdapter):
    """
    Generates pytest-formatted Python test files.

    Uses Jinja2 templates to render each TestSuite into a _test.py file.
    A conftest.py with common fixtures is auto-generated on first run.
    """

    def __init__(self):
        self._env = Environment(trim_blocks=True, lstrip_blocks=True)

    def format_name(self) -> str:
        return "pytest"

    def write(
        self, suites: list[TestSuite], context: GenerationContext
    ) -> list[str]:
        output_dir = Path(context.output_dir) / "pytest"
        output_dir.mkdir(parents=True, exist_ok=True)

        template = self._env.from_string(PYTEST_TEMPLATE)
        generated_files: list[str] = []

        for suite in suites:
            filename = self._sanitize_filename(suite.name) + "_test.py"
            filepath = output_dir / filename

            content = template.render(
                suite=suite,
                generation_time=datetime.now().isoformat(),
                version="1.0.0",
            )
            filepath.write_text(content, encoding="utf-8")
            generated_files.append(str(filepath))

        # Generate conftest.py with shared fixtures
        conftest = output_dir / "conftest.py"
        if not conftest.exists():
            conftest.write_text(CONFTEST_TEMPLATE, encoding="utf-8")
            generated_files.append(str(conftest))

        return generated_files

    def _sanitize_filename(self, name: str) -> str:
        """Remove illegal characters from filenames."""
        import re
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        name = name.replace(" ", "_").replace("-", "_")
        return name


CONFTEST_TEMPLATE = '''# -*- coding: utf-8 -*-
"""
TestGen Common pytest fixtures
"""
import pytest


@pytest.fixture
def base_url():
    """API base URL fixture."""
    return "http://localhost:8000"


@pytest.fixture
def api_client(base_url):
    """HTTP API client fixture using requests.Session."""
    import requests
    class APIClient:
        def __init__(self, base_url):
            self.base_url = base_url
            self.session = requests.Session()

        def request(self, method, path, **kwargs):
            url = f"{self.base_url}{path}"
            return self.session.request(method, url, **kwargs)

        def get(self, path, **kwargs):
            return self.request("GET", path, **kwargs)

        def post(self, path, **kwargs):
            return self.request("POST", path, **kwargs)

        def put(self, path, **kwargs):
            return self.request("PUT", path, **kwargs)

        def delete(self, path, **kwargs):
            return self.request("DELETE", path, **kwargs)

    return APIClient(base_url)
'''
