import os, json
from openai import AzureOpenAI
from .prompt_manager import PromptManager

class LLMService:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.deployment = config.get("deployment", "gpt-4o-mini")  # ім'я деплойменту в Azure
        self.temperature = config.get("temperature", 0.2)
        self.max_tokens = config.get("max_tokens", 700)
        self.prompts_dir = config.get("prompts_dir", "qa_bugs/prompts")

        # Azure специфіка
        self.client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_KEY"),
            api_version=config.get("api_version", "2024-05-01-preview"),
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        )
        self.pm = PromptManager(self.prompts_dir)

    def analyze_metric(self, metric_id: str, payload: dict) -> str:
        if not self.enabled:
            return ""
        prompt = self.pm.load_metric_prompt(metric_id)
        context = json.dumps(payload, ensure_ascii=False, indent=2)
        full_prompt = prompt.replace("{{context_json}}", context)

        resp = self.client.chat.completions.create(
            model=self.deployment,   # 👈 тут вказуємо ім’я деплойменту
            messages=[{"role": "user", "content": full_prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        return resp.choices[0].message.content

    def summarize(self, metrics_payloads: dict) -> str:
        if not self.enabled:
            return ""
        prompt = self.pm.load_summary_prompt()
        context = json.dumps(metrics_payloads, ensure_ascii=False, indent=2)
        full_prompt = prompt.replace("{{metrics_context_json}}", context)

        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        return resp.choices[0].message.content
