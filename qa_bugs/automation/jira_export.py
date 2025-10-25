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

import requests


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
                if attempt <= self.cfg.max_retries:
                    self._backoff_sleep(attempt, None)
                    continue
                raise e

            if resp.status_code == 429:
                if attempt <= self.cfg.max_retries:
                    self._backoff_sleep(attempt, resp.headers.get("Retry-After"))
                    continue
            if 500 <= resp.status_code < 600:
                if attempt <= self.cfg.max_retries:
                    self._backoff_sleep(attempt, None)
                    continue

            resp.raise_for_status()
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

        try:
            while True:
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

                # Write page
                written = self.exporter.write_page(issues)
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

                # Prepare for next loop
                next_token = returned_next

                if self._interrupted:
                    break
                if is_last or not next_token:
                    is_complete = True
                    break

        except requests.HTTPError as e:
            sys.stderr.write(f"HTTP error: {e.response.status_code} {e.response.text}\n")
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")

        return exported_total, is_complete


# =========================
# CLI
# =========================

def parse_args():
    ap = argparse.ArgumentParser(description="Export Jira issues via /rest/api/3/search/jql (OOP, resume-safe)")
    ap.add_argument("--site", required=True, help="https://your-domain.atlassian.net")
    ap.add_argument("--email", required=True, help="Account email")
    ap.add_argument("--token", required=True, help="API token")
    ap.add_argument("--jql", required=True, help='e.g. "project = HSP ORDER BY created DESC"')
    ap.add_argument("--fields", default=",".join(DEFAULT_FIELDS),
                    help="Comma-separated field names (or customfield_xxxxx). Empty string => no fields array.")
    ap.add_argument("--expand", default="", help="Comma-separated expand values")
    ap.add_argument("--max-results", type=int, default=100, help="Page size (typical 100)")
    ap.add_argument("--format", choices=["csv", "jsonl"], default="csv", help="Output format")
    ap.add_argument("--out", required=True, help="Output file path (append mode)")
    ap.add_argument("--checkpoint", default="", help="Checkpoint file path (JSON). If omitted, resume is disabled")
    ap.add_argument("--method", choices=["GET", "POST"], default="GET", help="HTTP method to use")
    ap.add_argument("--timeout", type=int, default=90, help="HTTP timeout seconds")
    ap.add_argument("--retries", type=int, default=6, help="Max retries for transient errors")
    return ap.parse_args()


def make_exporter(fmt: str, out_path: str) -> BaseExporter:
    return CsvExporter(out_path) if fmt == "csv" else JsonlExporter(out_path)


def main():
    args = parse_args()
    fields = None if args.fields.strip() == "" else [f.strip() for f in args.fields.split(",") if f.strip()]
    expand = None if args.expand.strip() == "" else args.expand

    cfg = JiraConfig(
        site=args.site,
        email=args.email,
        token=args.token,
        method=args.method,
        timeout_s=args.timeout,
        max_retries=args.retries,
    )
    client = JiraSearchClient(cfg)
    exporter = make_exporter(args.format, args.out)
    ckpt = CheckpointStore(args.checkpoint if args.checkpoint.strip() else None)

    meta = {
        "site": args.site,
        "jql": args.jql,
        "format": args.format,
        "out": args.out,
    }

    runner = ExportRunner(
        client=client,
        exporter=exporter,
        checkpoint=ckpt,
        jql=args.jql,
        fields=fields,
        max_results=args.max_results,
        expand=expand,
        meta=meta,
    )

    count, complete = runner.run()
    status = "complete" if complete else "incomplete (resume available)"
    print(f"Exported {count} issues → {args.out} — {status}")


if __name__ == "__main__":
    main()
