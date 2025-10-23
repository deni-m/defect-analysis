from pathlib import Path

class PromptManager:
    def __init__(self, prompts_dir: str):
        self.prompts_dir = Path(prompts_dir)

    def load_metric_prompt(self, metric_id: str) -> str:
        p = self.prompts_dir / "metric" / f"{metric_id}.md"
        return p.read_text(encoding="utf-8") if p.exists() else f"No prompt available for metric {metric_id}"

    def load_summary_prompt(self) -> str:
        p = self.prompts_dir / "summary" / "overall.md"
        return p.read_text(encoding="utf-8") if p.exists() else "No summary prompt available"
