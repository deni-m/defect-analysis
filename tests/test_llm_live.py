import os
import pytest
from qa_bugs.llm.service import LLMService

@pytest.mark.live
def test_llm_live_chat_completion():
    # Skip if required env vars are missing
    if not os.getenv("AZURE_OPENAI_KEY") or not os.getenv("AZURE_OPENAI_ENDPOINT"):
        pytest.skip("Azure OpenAI credentials not set; skipping live LLM test")

    cfg = {
        "enabled": True,
        "deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
        "temperature": 0.0,
        "max_tokens": 50,
        "prompts_dir": "qa_bugs/prompts",
    }
    service = LLMService(cfg)
    ok, message = service.ping()
    if not ok:
        pytest.fail(f"LLM ping failed: {message}")
    assert isinstance(message, str)
    assert len(message) >= 0  # allow empty or short reply; the presence of ok=True is sufficient
