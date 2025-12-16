from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class PromptManager:
    def __init__(self, prompts_dir: str):
        prompts_path = Path(prompts_dir)
        
        # If the path is relative, resolve it relative to this module's location
        if not prompts_path.is_absolute():
            # Get the qa_bugs package directory (parent of llm directory)
            qa_bugs_dir = Path(__file__).parent.parent
            prompts_path = qa_bugs_dir / prompts_dir
            
            # If still not found, try relative to qa_bugs directory
            if not prompts_path.exists():
                # Remove "qa_bugs/" prefix if present and resolve
                if prompts_dir.startswith("qa_bugs/"):
                    prompts_path = qa_bugs_dir / prompts_dir.replace("qa_bugs/", "")
        
        self.prompts_dir = prompts_path
        logger.debug(f"PromptManager initialized with prompts_dir: {self.prompts_dir} (exists: {self.prompts_dir.exists()})")

    def load_metric_prompt(self, metric_id: str) -> str:
        p = self.prompts_dir / "metric" / f"{metric_id}.md"
        if p.exists():
            logger.debug(f"Loading metric prompt from: {p}")
            return p.read_text(encoding="utf-8")
        else:
            logger.warning(f"Metric prompt file not found: {p}")
            return f"No prompt available for metric {metric_id}"

    def load_summary_prompt(self) -> str:
        p = self.prompts_dir / "summary" / "overall.md"
        if p.exists():
            logger.debug(f"Loading summary prompt from: {p}")
            return p.read_text(encoding="utf-8")
        else:
            logger.warning(f"Summary prompt file not found: {p}")
            return "No summary prompt available"
