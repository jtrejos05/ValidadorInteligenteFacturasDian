import os

import pytest

# Tests never call a real model, whatever the developer's environment has.
os.environ["DIAN_LLM_PROVIDER"] = "mock"

from app.ai.llm import MockLLM  # noqa: E402
from evals.cases import EVAL_TODAY  # noqa: E402


@pytest.fixture
def llm():
    return MockLLM()


@pytest.fixture
def today():
    return EVAL_TODAY
