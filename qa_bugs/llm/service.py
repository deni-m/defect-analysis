import os, time, re
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Tuple
from openai import AzureOpenAI
from .prompt_manager import PromptManager


@dataclass
class _LLMDebugEvent:
    phase: str
    ok: bool
    latency_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    prompt_chars: int | None = None
    prompt_tokens_requested: int | None = None
    response_chars: int | None = None
    model: str | None = None
    api_version: str | None = None
    endpoint: str | None = None
    metric_id: str | None = None

    def to_line(self) -> str:
        parts = [f"phase={self.phase}", f"ok={self.ok}"]
        if self.metric_id:
            parts.append(f"metric={self.metric_id}")
        if self.latency_ms is not None:
            parts.append(f"latency_ms={self.latency_ms:.1f}")
        if self.prompt_chars is not None:
            parts.append(f"prompt_chars={self.prompt_chars}")
        if self.response_chars is not None:
            parts.append(f"response_chars={self.response_chars}")
        if self.error_type:
            parts.append(f"error_type={self.error_type}")
        if self.error_message:
            parts.append(f"error_message={self.error_message}")
        if self.model:
            parts.append(f"model={self.model}")
        if self.api_version:
            parts.append(f"api_version={self.api_version}")
        if self.endpoint:
            parts.append(f"endpoint={self.endpoint}")
        return " | ".join(parts)


class LLMService:
    def __init__(self, config: dict, full_config: dict | None = None, log_dir: str | None = None):
        self.enabled = config.get("enabled", False)
        # Allow env var override for deployment name
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or config.get("deployment", "gpt-4o-mini")
        self.temperature = config.get("temperature", 0.2)
        self.max_tokens = config.get("max_tokens", 700)
        self.prompts_dir = config.get("prompts_dir", "qa_bugs/prompts")
        self.debug = config.get("debug", False)
        self.log_prompts = config.get("log_prompts", False)
        self._log_dir = Path(log_dir) if (log_dir and self.log_prompts) else None
        self.api_version = config.get("api_version", "2024-05-01-preview")
        # Trimming / compression settings
        self.table_row_limit = int(config.get("table_row_limit", 200))  # per table
        self.max_prompt_chars = int(config.get("max_prompt_chars", 120_000))  # safety bound under model token limit
        self.summary_table_row_limit = int(config.get("summary_table_row_limit", 40))  # for overall summary

        # Store full config for dynamic prompt templating (e.g., status lists from metrics.params)
        self.full_config = full_config or {}

        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_KEY")

        self.client = AzureOpenAI(
            api_key=api_key,
            api_version=self.api_version,
            azure_endpoint=endpoint,
        )
        self.pm = PromptManager(self.prompts_dir)
        if self._log_dir:
            try:
                self._log_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                self._log_dir = None  # disable if cannot create

    # --- internal helpers -------------------------------------------------
    def _log(self, event: _LLMDebugEvent):
        if not self.debug:
            return
        # Print single-line structured log
        print(f"[LLM] {event.to_line()}")

    def _chat(self, model: str, messages: list[Dict[str, Any]], temperature: float, max_tokens: int, metric_id: str | None = None) -> Tuple[bool, Any, str | None]:
        start = time.time()
        prompt_text = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_tokens,
            )
            latency = (time.time() - start) * 1000
            txt = resp.choices[0].message.content or ""
            self._log(_LLMDebugEvent(
                phase="chat", ok=True, latency_ms=latency,
                prompt_chars=len(prompt_text), response_chars=len(txt),
                model=model, api_version=self.api_version, endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"), metric_id=metric_id
            ))
            self._maybe_persist(metric_id or "unknown", prompt_text, txt, error=None)
            return True, txt, None
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._log(_LLMDebugEvent(
                phase="chat", ok=False, latency_ms=latency,
                error_type=type(e).__name__, error_message=str(e),
                prompt_chars=len(prompt_text), model=model,
                api_version=self.api_version, endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"), metric_id=metric_id
            ))
            self._maybe_persist(metric_id or "unknown", prompt_text, None, error=f"{type(e).__name__}: {e}")
            return False, None, f"{type(e).__name__}: {e}"

    # --- public API -------------------------------------------------------
    def _apply_config_templates(self, prompt_template: str, metric_id: str) -> str:
        """Apply config-based template substitutions to the prompt.

        Supports placeholders like:
        - {{open_statuses}}: comma-separated list of open statuses from config
        - {{closed_statuses}}: comma-separated list of closed statuses from config
        """
        result = prompt_template
        metrics_params = self.full_config.get("metrics", {}).get("params", {})
        metric_params = metrics_params.get(metric_id, {})

        if "open_statuses" in metric_params:
            statuses = metric_params["open_statuses"]
            if isinstance(statuses, list):
                formatted = ", ".join(f'"{s}"' for s in statuses)
                result = result.replace("{{open_statuses}}", formatted)

        if "closed_statuses" in metric_params:
            statuses = metric_params["closed_statuses"]
            if isinstance(statuses, list):
                formatted = ", ".join(f'"{s}"' for s in statuses)
                result = result.replace("{{closed_statuses}}", formatted)

        return result

    def analyze_metric(self, metric_id: str, payload: dict) -> str:
        if not self.enabled:
            return ""
        prompt_template = self.pm.load_metric_prompt(metric_id)
        trimmed_payload = self._trim_payload(payload, self.table_row_limit)
        # ALWAYS CSV
        context_csv = self._payload_to_csv(trimmed_payload)
        # Apply config-based template substitutions, then data context
        full_prompt = (
            self._apply_config_templates(prompt_template, metric_id)
            .replace("{{context}}", context_csv)
        )
        context = context_csv
        if len(full_prompt) > self.max_prompt_chars:
            full_prompt = full_prompt[: self.max_prompt_chars] + "\n...TRUNCATED..."
        ok, txt, err = self._chat(
            model=self.deployment,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            metric_id=metric_id,
        )
        if ok:
            return txt
        fallback_prompt = f"You are a concise analyst. Summarize metric {metric_id} in <=50 words based on CSV: {context[:1500]}"
        ok2, txt2, err2 = self._chat(
            model=self.deployment,
            messages=[{"role": "user", "content": fallback_prompt}],
            temperature=0.0,
            max_tokens=120,
            metric_id=metric_id,
        )
        if ok2:
            return txt2 + f"\n(Fallback used due to error: {err})"
        return f"LLM error primary={err} fallback={err2}"


    def summarize_texts(self, metric_texts: dict[str, str]) -> str:
        """Summarize already generated metric insight texts instead of raw payloads.

        metric_texts: mapping metric_id -> analysis text (plain markdown or summary string).
        We format as structured markdown with clear metric labels for better LLM comprehension.
        """
        if not self.enabled:
            return "LLM disabled"
        prompt_template = self.pm.load_summary_prompt()
        # Build structured markdown representation with clear metric sections
        lines = []
        for mid, txt in metric_texts.items():
            if not txt:
                continue
            # Clean up the text: remove excessive newlines, normalize spacing
            safe = txt.replace("\n\n", " | ").replace("\n", " ").strip()
            # truncate overly long per-metric text to keep total small
            if len(safe) > 2000:
                safe = safe[:2000] + "..."
            # Format as: ## metric_name\ninsight_text
            lines.append(f"## {mid}\n{safe}")
        context_block = "\n\n".join(lines)
        full_prompt = (
            prompt_template
            .replace("{{metrics_context}}", context_block)            
        )
        if len(full_prompt) > self.max_prompt_chars:
            full_prompt = full_prompt[: self.max_prompt_chars]
        ok, txt, err = self._chat(
            model=self.deployment,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            metric_id="__summary_texts__",
        )
        if ok:
            return txt
        # fallback minimal summary
        fallback_prompt = f"Summarize these metric insights: {context_block[:1500]}"
        ok2, txt2, err2 = self._chat(
            model=self.deployment,
            messages=[{"role": "user", "content": fallback_prompt}],
            temperature=0.0,
            max_tokens=160,
            metric_id="__summary_texts_fallback__",
        )
        if ok2:
            return txt2
        return f"LLM error primary={err} fallback={err2}"

    def ping(self) -> tuple[bool, str]:
        """Minimal health check for Azure OpenAI deployment.

        Returns (ok, message). Does NOT raise on API failures; converts them to (False, details).
        """
        if not self.enabled:
            return False, "LLM disabled"
        ok, txt, err = self._chat(
            model=self.deployment,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            max_tokens=5,
            metric_id="__ping__",
        )
        if ok:
            return True, (txt.strip() or "empty response")
        return False, f"error: {err}"

    # --- trimming helpers -------------------------------------------------
    def _trim_payload(self, payload: dict, row_limit: int) -> dict:
        """Limit rows per table and annotate truncation for transparency.

        Note: Do not add truncation markers for LLM-specific tables (they're already optimized).
        """
        out = {
            "metric_id": payload.get("metric_id"),
            "summary": payload.get("summary"),
            "tables": {},
        }
        tables = payload.get("tables", {})
        # List of table names that should not have truncation markers added
        llm_optimized_tables = {"cumulative_daily", "cumulative_weekly", "cumulative_monthly", "status_by_severity_llm"}

        for name, rows in tables.items():
            if not isinstance(rows, list):
                continue
            if len(rows) > row_limit:
                trimmed = rows[:row_limit]
                # Only add truncation marker for non-LLM-optimized tables
                if name not in llm_optimized_tables:
                    trimmed.append({"_truncated": True, "_original_rows": len(rows)})
                out["tables"][name] = trimmed
            else:
                out["tables"][name] = rows
        return out

    def _maybe_persist(self, metric_id: str, prompt: str, response: str | None, error: str | None):
        if not self._log_dir:
            return
        try:
            # One file per interaction (metric or summary).
            safe_id = metric_id.replace("/", "_")
            fname = f"llm_{safe_id}.txt"
            path = self._log_dir / fname
            with path.open("w", encoding="utf-8") as f:
                f.write(f"metric_id: {metric_id}\n")
                f.write(f"timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
                f.write(f"model: {self.deployment}\n")
                f.write(f"api_version: {self.api_version}\n")
                f.write(f"prompt_chars: {len(prompt)}\n")
                if error:
                    f.write(f"error: {error}\n")
                f.write("\n--- PROMPT ---\n")
                f.write(prompt)
                f.write("\n--- RESPONSE ---\n")
                if response is not None:
                    f.write(response)
                else:
                    f.write("<no response due to error>")
        except Exception as e:
            self._log(_LLMDebugEvent(phase="persist", ok=False, error_type=type(e).__name__, error_message=str(e), model=self.deployment))

    # --- CSV helpers (always CSV now) -------------------------------------
    def _escape_csv(self, val: Any) -> str:
        if val is None:
            return ""
        s = str(val)
        if any(c in s for c in [',', '\n', '"']) or s.strip() != s:
            s = '"' + s.replace('"', '""') + '"'
        return s

    def _shorten_iso_midnight(self, val: Any) -> Any:
        if not isinstance(val, str):
            return val
        # Match YYYY-MM-DDT00:00:00 (optionally with Z / timezone not specified in example)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00", val):
            return val[:10]
        return val

    def _payload_to_csv(self, payload: dict) -> str:
        metric_id = self._shorten_iso_midnight(payload.get('metric_id'))
        summary = self._shorten_iso_midnight(payload.get('summary'))
        parts = [f"metric_id,{metric_id}", f"summary,{self._escape_csv(summary)}"]
        tables = payload.get("tables", {})
        for tname, rows in tables.items():
            if not isinstance(rows, list) or not rows:
                continue
            parts.append("")
            parts.append(f"# table:{tname}")
            headers: list[str] = []
            for r in rows:
                if isinstance(r, dict):
                    for k in r.keys():
                        if k not in headers:
                            headers.append(k)
            parts.append(",".join(headers))
            for r in rows:
                if not isinstance(r, dict):
                    continue
                row_vals = []
                for h in headers:
                    v = self._shorten_iso_midnight(r.get(h))
                    row_vals.append(self._escape_csv(v))
                parts.append(",".join(row_vals))
        return "\n".join(parts)

    def _multi_payload_to_csv(self, multi: dict) -> str:
        blocks: list[str] = []
        for mid, payload in multi.items():
            blocks.append(f"## metric:{mid}")
            blocks.append(self._payload_to_csv(payload))
            blocks.append("")
        return "\n".join(blocks)
