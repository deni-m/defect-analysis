#!/usr/bin/env python3
"""
OOP Jira Enhanced JQL Exporter (v3 /search/jql, token-based pagination).

Usage:
  python jira_export_oop.py \
    --site https://your-domain.atlassian.net \
    --email you@example.com \
    --token <api_token> \
    --jql "project = HSP ORDER BY created DESC" \
    --fields key,summary,issuetype,status,priority,assignee,reporter,created,updated \
    --max-results 100 \
    --format csv \
    --out issues.csv \
    --checkpoint issues.ckpt.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Protocol
from pathlib import Path
import logging
logger = logging.getLogger("jira_export")

import requests

# Optional .env loading
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


# =========================
# Utility / Types
# =========================

DEFAULT_FIELDS = [
    "summary",
    "issuetype",
    "status",
    "priority",
    "assignee",
    "reporter",
    "created",
    "updated",
]

CSV_HEADERS = [
    "key", "summary", "issuetype", "status", "priority",
    "assignee", "assignee_accountId", "reporter", "created", "updated", "projectKey"
]


def flatten_issue(issue: Dict) -> Dict:
    f = issue.get("fields", {}) or {}

    def g(path, default=""):
        cur = f
        for p in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return default
        if isinstance(cur, dict):
            return cur.get("name") or cur.get("displayName") or cur.get("key") or cur.get("id") or default
        return cur if cur is not None else default

    return {
        "key": issue.get("key", ""),
        "summary": f.get("summary", ""),
        "issuetype": g("issuetype.name"),
        "status": g("status.name"),
        "priority": g("priority.name"),
        "assignee": g("assignee.displayName"),
        "assignee_accountId": g("assignee.accountId"),
        "reporter": g("reporter.displayName"),
        "created": f.get("created", ""),
        "updated": f.get("updated", ""),
        "projectKey": g("project.key"),
    }


# =========================
# Checkpointing
# =========================

class CheckpointStore:
    """Simple JSON checkpoint store with atomic writes."""

    def __init__(self, path: Optional[str]):
        self.path = path

    def load(self) -> Dict:
        if not self.path or not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self, data: Dict) -> None:
        if not self.path:
            return
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


# =========================
# Exporters
# =========================

class BaseExporter(Protocol):
    def prepare(self) -> None: ...
    def write_page(self, issues: Iterable[Dict]) -> int: ...


class CsvExporter:
    def __init__(self, out_path: str):
        self.out_path = out_path

    def prepare(self) -> None:
        need_header = True
        if os.path.exists(self.out_path) and os.path.getsize(self.out_path) > 0:
            need_header = False
        if need_header:
            with open(self.out_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(CSV_HEADERS)

    def write_page(self, issues: Iterable[Dict]) -> int:
        rows = [flatten_issue(i) for i in issues]
        if not rows:
            return 0
        with open(self.out_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            for r in rows:
                w.writerow(r)
        return len(rows)


class JsonlExporter:
    def __init__(self, out_path: str):
        self.out_path = out_path

    def prepare(self) -> None:
        # Ensure the file exists
        open(self.out_path, "a", encoding="utf-8").close()

    def write_page(self, issues: Iterable[Dict]) -> int:
        n = 0
        with open(self.out_path, "a", encoding="utf-8") as f:
            for it in issues:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
                n += 1
        return n


# =========================
# Jira Client
# =========================

@dataclass
class JiraConfig:
    site: str
    email: str
    token: str
    method: str = "GET"          # GET or POST
    timeout_s: int = 90
    max_retries: int = 6


class JiraSearchClient:
    """Client for Jira Cloud v3 enhanced JQL search (/rest/api/3/search/jql)."""

    def __init__(self, cfg: JiraConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.auth = (cfg.email, cfg.token)
        self.base_url = cfg.site.rstrip("/") + "/rest/api/3/search/jql"

    @staticmethod
    def _backoff_sleep(attempt: int, retry_after: Optional[str]) -> None:
        if retry_after is not None:
            try:
                ra = float(retry_after)
                if ra >= 0:
                    time.sleep(ra)
                    return
            except Exception:
                pass
        base = min(60, 2 ** attempt)
        time.sleep(base * 0.5 + (base * 0.5))

    def fetch_page(
        self,
        jql: str,
        fields: Optional[List[str]],
        max_results: int,
        next_token: Optional[str],
        expand: Optional[str],
    ) -> Dict:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        params = {"jql": jql}
        if fields:
            params["fields"] = fields
        if max_results:
            params["maxResults"] = max_results
        if expand:
            params["expand"] = expand
        if next_token:
            params["nextPageToken"] = next_token

        attempt = 0
        while True:
            attempt += 1
            logger.debug(
                "fetch_page attempt=%s next_token=%s max_results=%s method=%s",
                attempt, next_token, max_results, self.cfg.method
            )
            try:
                if self.cfg.method == "GET":
                    resp = self.session.get(
                        self.base_url, headers=headers, params=params,
                        auth=self.auth, timeout=self.cfg.timeout_s
                    )
                else:
                    body = {"jql": jql, "fields": fields or [], "maxResults": max_results}
                    if expand:
                        body["expand"] = expand
                    if next_token:
                        body["nextPageToken"] = next_token
                    resp = self.session.post(
                        self.base_url, headers=headers, json=body,
                        auth=self.auth, timeout=self.cfg.timeout_s
                    )
            except requests.RequestException as e:
                logger.warning("network error attempt=%s error=%s", attempt, e)
                if attempt <= self.cfg.max_retries:
                    self._backoff_sleep(attempt, None)
                    continue
                raise e

            if resp.status_code == 429:
                logger.warning("rate limited (429) attempt=%s retry_after=%s", attempt, resp.headers.get("Retry-After"))
                if attempt <= self.cfg.max_retries:
                    self._backoff_sleep(attempt, resp.headers.get("Retry-After"))
                    continue
            if 500 <= resp.status_code < 600:
                logger.warning("server error status=%s attempt=%s", resp.status_code, attempt)
                if attempt <= self.cfg.max_retries:
                    self._backoff_sleep(attempt, None)
                    continue

            resp.raise_for_status()
            logger.debug("fetch_page success status=%s", resp.status_code)
            return resp.json()


# =========================
# Orchestrator
# =========================

class ExportRunner:
    """Coordinates paging, writing, and checkpointing, with SIGINT-safe resume."""

    def __init__(
        self,
        client: JiraSearchClient,
        exporter: BaseExporter,
        checkpoint: CheckpointStore,
        jql: str,
        fields: Optional[List[str]],
        max_results: int,
        expand: Optional[str],
        meta: Optional[Dict] = None,
    ):
        self.client = client
        self.exporter = exporter
        self.checkpoint = checkpoint
        self.jql = jql
        self.fields = fields
        self.max_results = max_results
        self.expand = expand
        self.meta = meta or {}
        self._interrupted = False
        signal.signal(signal.SIGINT, self._sigint_handler)

    def _sigint_handler(self, signum, frame):
        self._interrupted = True

    def run(self) -> Tuple[int, bool]:
        """Returns (exported_count, is_complete)."""
        self.exporter.prepare()

        ckpt = self.checkpoint.load()
        next_token = ckpt.get("nextPageToken")
        pages_done = int(ckpt.get("pagesDone", 0))
        exported_total = int(ckpt.get("exportedTotal", 0))

        is_complete = False

        logger.info("run start jql=%s page_size=%s expand=%s resume_token=%s", self.jql, self.max_results, self.expand, next_token)
        try:
            while True:
                logger.debug("page_request pages_done=%s exported_total=%s next_token=%s", pages_done, exported_total, next_token)
                data = self.client.fetch_page(
                    jql=self.jql,
                    fields=self.fields,
                    max_results=self.max_results,
                    next_token=next_token,
                    expand=self.expand,
                )
                issues = data.get("issues", []) or []
                is_last = bool(data.get("isLast", False))
                returned_next = data.get("nextPageToken")
                logger.info(
                    "page_received page_index=%s issues=%s is_last=%s returned_next=%s",
                    pages_done + 1, len(issues), is_last, returned_next
                )

                # Write page
                written = self.exporter.write_page(issues)
                logger.debug("page_written count=%s cumulative=%s", written, exported_total + written)
                exported_total += written
                pages_done += 1

                # Save checkpoint AFTER successful write
                new_ckpt = {
                    "nextPageToken": returned_next,
                    "pagesDone": pages_done,
                    "exportedTotal": exported_total,
                    "lastWriteTs": int(time.time()),
                    **self.meta,
                }
                self.checkpoint.save(new_ckpt)
                logger.debug("checkpoint_saved pages_done=%s exported_total=%s next_token=%s", pages_done, exported_total, returned_next)

                # Prepare for next loop
                next_token = returned_next

                if self._interrupted:
                    logger.warning("interrupted_by_signal exported_total=%s", exported_total)
                    break
                if is_last or not next_token:
                    is_complete = True
                    logger.info("completed_all_pages exported_total=%s pages=%s", exported_total, pages_done)
                    break
        except requests.HTTPError as e:
            logger.error("http_error status=%s body=%s", e.response.status_code, e.response.text)
        except Exception as e:
            logger.exception("unexpected_error error=%s", e)
        logger.info("run_end exported_total=%s complete=%s", exported_total, is_complete)
        return exported_total, is_complete


# =========================
# CLI
# =========================

def make_exporter(fmt: str, out_path: str) -> BaseExporter:
    return CsvExporter(out_path) if fmt == "csv" else JsonlExporter(out_path)

def main():      
    # Environment-only configuration (CLI args removed for these settings)
    log_level = os.environ.get("JIRA_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    logger.info("startup version=enhanced logging_level=%s", log_level)

    site = os.environ.get("JIRA_URL")
    email = os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER")
    token = os.environ.get("JIRA_API_TOKEN")
    jql = os.environ.get("JIRA_JQL")

    if not all([site, email, token, jql]):
        logger.error("missing_required_env site=%s email=%s token=%s jql_present=%s",
                     bool(site), bool(email), bool(token), bool(jql))
        sys.exit(2)
    # NOTE: simplified fixed config (fields empty -> omitted)
    fields = DEFAULT_FIELDS
    expand = None
    page_size = 50
    out_path = "jira_issues.csv"
    checkpoint_path = ""
    fmt = "csv"
    method = "GET"
    timeout_s = 10
    retries = 3
    logger.info(
        "config site=%s user=%s jql_len=%s page_size=%s out=%s checkpoint=%s retries=%s timeout=%s",
        site, email, len(jql or ""), page_size, out_path, bool(checkpoint_path), retries, timeout_s
    )

    cfg = JiraConfig(
        site=site,
        email=email,
        token=token,
        method=method,
        timeout_s=timeout_s,
        max_retries=retries,
    )

    meta: Dict = {
        "site": site,
        "jql": jql,
        "fields": fields,
        "format": fmt,
        "out": out_path,
        "checkpoint": checkpoint_path,
        "method": method,
    }

    exporter = make_exporter(fmt, out_path)
    checkpoint = CheckpointStore(checkpoint_path if checkpoint_path else None)
    runner = ExportRunner(
        client=JiraSearchClient(cfg),
        exporter=exporter,
        checkpoint=checkpoint,
        jql=jql,
        fields=fields,
        max_results=page_size,
        expand=expand,
        meta=meta,
    )

    print(
        f"[jira-export] site={cfg.site} method={cfg.method} page_size={page_size} "
        f"fields={'<omitted>' if fields is None else 0} "
        f"format={fmt} out={out_path} checkpoint={'on' if checkpoint_path else 'off'}"
    )
    exported, complete = runner.run()
    logger.info("summary exported=%s complete=%s", exported, complete)
    print(f"[jira-export] exported={exported} complete={complete}")


if __name__ == "__main__":
    main()
