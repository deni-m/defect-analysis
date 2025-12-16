#!/usr/bin/env python3
"""
Jira export module using unified JiraClient (classic & enhanced JQL supported).
Environment-driven configuration (no CLI).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd

# Support running as a standalone script without installing the package
if __package__ is None or __package__ == "":
    try:
        # project root = .../bug-analytics
        _project_root = Path(__file__).resolve().parents[2]
        if str(_project_root) not in sys.path:
            sys.path.insert(0, str(_project_root))
    except Exception:
        pass

# Re-import after path adjustment (idempotent if already imported)
from qa_bugs.automation.jira_client import JiraClient, JiraClientError, flatten_issue  # type: ignore

logger = logging.getLogger("jira_export")


def _get_field_value(raw):
    """
    Convert Jira field payloads to a scalar representation:
      - [ { "value": "A" }, { "value": "B"} ] -> "A,B"
      - { "value": "X" } -> "X"
      - { "name": "Y" }  -> "Y" (if no 'value')
      - Otherwise (complex) -> JSON string
    """
    if isinstance(raw, list):
        collected = []
        for item in raw:
            if isinstance(item, dict) and "value" in item:
                collected.append(str(item["value"]))
            else:
                return json.dumps(raw, ensure_ascii=False)
        return ",".join(collected)
    if isinstance(raw, dict):
        if "value" in raw and isinstance(raw["value"], (str, int, float)):
            return raw["value"]
        if "name" in raw and isinstance(raw["name"], (str, int, float)):
            return raw["name"]
        return json.dumps(raw, ensure_ascii=False)
    return raw


def _normalize_date_columns(df: pd.DataFrame, columns: list[str]) -> None:
    """
    In-place: trim Jira datetime strings like '2025-02-07T12:20:39.379+0000'
    to '2025-02-07'. Skips values not starting with YYYY-MM-DDT.
    """
    for col in columns:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(
            lambda v: (v[:10] if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and "T" in v else v)
        )


def export_issues(
    client: JiraClient,
    jql: str,
    output_csv: Path,
    fields: List[str],
    limit: Optional[int],
) -> int:
    issue_rows = []
    all_fields_mode = any(f.lower() in ("*all", "*") for f in fields)

    issue_iterator = client.get_issues(
        jql,
        fields=fields,
        expand="names",
        limit=limit,
        include_total=True,
    )
    for issue in issue_iterator:
        if all_fields_mode:
            fields_dict = issue.get("fields", {}) or {}
            issue_row = {"key": issue.get("key")}
            for field_name, field_value in fields_dict.items():
                if isinstance(field_value, (str, int, float, bool)) or field_value is None:
                    issue_row[field_name] = field_value
                else:
                    issue_row[field_name] = _get_field_value(field_value)
            issue_rows.append(issue_row)
        else:
            # Use requested fields list (ensure 'key' present and preserve order)
            requested = ["key"] + [field for field in fields if field != "key" and field.lower() not in ("*all", "*")]
            flattened_issue = flatten_issue(issue)
            raw_fields = issue.get("fields", {}) or {}
            issue_row: dict[str, object] = {}
            for field_name in requested:
                value = flattened_issue.get(field_name)
                if value is None or value == "":
                    raw_value = raw_fields.get(field_name)
                    if isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
                        value = raw_value
                    else:
                        value = _get_field_value(raw_value)
                issue_row[field_name] = value
            issue_rows.append(issue_row)

    if not issue_rows:
        logger.warning("No issues returned for JQL: %s", jql)
        return 0

    if all_fields_mode:
        all_field_names = {"key"}
        for issue_row in issue_rows:
            all_field_names.update(issue_row.keys())
        ordered_columns = ["key"] + sorted(name for name in all_field_names if name != "key")
        df = pd.DataFrame(issue_rows).reindex(columns=ordered_columns)
        mode_label = "all-fields"
    else:
        df = pd.DataFrame(issue_rows)
        mode_label = "requested"

    # NEW: normalize date-only columns
    _normalize_date_columns(df, ["created", "resolved", "resolutiondate"])

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    logger.info("Wrote %s issues (%s) -> %s", len(df), mode_label, output_csv)
    return len(df)


def export_field_mapping(field_map: dict[str, str], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["field_id", "display_name"])
        for field_id, display_name in field_map.items():
            w.writerow([field_id, display_name])
    logger.info("Wrote %s field definitions -> %s", len(field_map), output_path)
    return output_path


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    # --------- ENV CONFIG ----------
    site = os.environ.get("JIRA_URL")
    email = os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER")
    token = os.environ.get("JIRA_API_TOKEN")
    #jql = 'project=MCKORD AND "Waves[Dropdown]" = "Wave 05" and issuetype = Bug'
    jql = 'project=MCKORD AND "Waves[Dropdown]" = "Wave 09" AND (issuetype = Bug or (issuetype = "sub-task" and summary~"[bug]"))'
    
    fields = None #["*all"]  # Set to ["*all"] or ["*"] to export every field; otherwise supply explicit field names.
    limit = None
    output_path = Path("jira_issues_mck_w9.csv")
    field_map_out = Path("jira_fields.csv")
    # Fields
    if not fields:
        fields = ["key","issuetype", "status", "priority", "created", "resolutiondate","customfield_12200"]

    # Auth: prefer basic (email+token) else bearer (token only)
    if email and token:
        auth: str | tuple[str, str] = (email, token)
    else:
        auth = token  # bearer
    # --------------------------------

    client = JiraClient(
        base_url=site,
        auth=auth,
        default_batch=50,
        max_retries=3,
    )

    #field_map = client.get_field_display_map()
    #export_field_mapping(field_map, field_map_out)

    try:
        export_issues(
            client=client,
            jql=jql,
            output_csv=output_path,
            fields=fields,
            limit=limit,
        )
    except JiraClientError as e:
        logger.error("Failed to export issues: %s", e)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
