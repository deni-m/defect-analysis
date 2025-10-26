from __future__ import annotations

import time
import logging
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple

import requests
from requests import Response, Session

logger = logging.getLogger(__name__)


class JiraClientError(RuntimeError):
    """Raised for non-recoverable JIRA client errors."""

def flatten_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a Jira issue payload into a simple dict of commonly used fields.
    Mirrors (and replaces) previous implementation in jira_export.py.
    """
    f = issue.get("fields", {}) or {}

    def g(container: Dict[str, Any], path: str, default: str = "") -> Any:
        cur: Any = container
        for p in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return default
        if isinstance(cur, dict):
            for k in ("name", "displayName", "key", "id"):
                if k in cur and cur[k]:
                    return cur[k]
            return default
        return cur if cur is not None else default

    return {
        "key": issue.get("key", ""),
        "summary": f.get("summary", ""),
        "issuetype": g(f, "issuetype.name"),
        "status": g(f, "status.name"),
        "priority": g(f, "priority.name"),
        "assignee": g(f, "assignee.displayName"),
        "assignee_accountId": g(f, "assignee.accountId"),
        "reporter": g(f, "reporter.displayName"),
        "created": f.get("created", ""),
        "updated": f.get("updated", ""),
        "resolutiondate": f.get("resolutiondate", ""),
        "projectKey": g(f, "project.key"),
    }


class JiraClient:
    """
    Minimal JIRA REST API client (search + issue fetch) with:
      - Token or basic auth (pass tuple for basic, string for bearer/token)
      - Pagination (startAt / maxResults)
      - Retry with exponential backoff on transient errors / 429
      - Optional hard limit of issues
    """

    def __init__(
        self,
        base_url: str,
        auth: str | tuple[str, str],
        *,
        api_root: str = "/rest/api/2",
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.6,
        ratelimit_sleep: int = 60,
        verify: bool = True,
        default_batch: int = 100,
        user_agent: str = "qa-bugs-jira-client/1.0",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_root = api_root.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.ratelimit_sleep = ratelimit_sleep
        self.default_batch = default_batch
        self.session: Session = requests.Session()
        self.session.verify = verify
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

        # Auth handling
        if isinstance(auth, tuple):
            self.session.auth = auth  # basic
        else:
            # Accept plain token or "Bearer ..." already formatted
            token = auth.strip()
            if not token.lower().startswith("bearer "):
                self.session.headers["Authorization"] = f"Bearer {token}"
            else:
                self.session.headers["Authorization"] = token

    def search(
        self,
        jql: str,
        *,
        fields: Optional[Iterable[str]] = None,
        expand: Optional[Iterable[str]] = None,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
        include_total: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return list of issues (fully materialized)."""
        return list(
            self.get_issues(
                jql,
                fields=fields,
                expand=expand,
                batch_size=batch_size,
                limit=limit,
                include_total=include_total,
            )
        )

    def get_issues(
        self,
        jql: str,
        *,
        fields: Optional[Iterable[str]] = None,
        expand: Optional[Iterable[str]] = None,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
        include_total: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Enhanced JQL (Cloud v3) iterator using nextPageToken pagination:
        /rest/api/3/search/jql

        Falls back to classic iter_issues if server rejects endpoint.
        """
        size = batch_size or self.default_batch
        next_token: Optional[str] = None
        yielded = 0
        first_total_logged = False
        page_index = 0  # NEW: page counter

        while True:
            page = self.search_page(
                jql=jql,
                max_results=size,
                fields=fields,
                expand=expand,
                next_token=next_token,
            )
            issues = page.get("issues", []) or []
            page_index += 1
            is_last_flag = bool(page.get("isLast")) or not page.get("nextPageToken")

            if include_total and not first_total_logged:
                if "total" in page:
                    logger.info("JIRA enhanced search total=%s (may exceed run limit)", page.get("total"))
                first_total_logged = True

            # NEW: progress log before yielding issues
            logger.info(
                "jira.get_issues page=%d size=%d cumulative_after=%d next_token=%s is_last=%s",
                page_index,
                len(issues),
                yielded + len(issues),
                "yes" if page.get("nextPageToken") else "no",
                is_last_flag,
            )

            for issue in issues:
                yield issue
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

            is_last = is_last_flag
            next_token = page.get("nextPageToken")

            if is_last:
                break
            if limit is not None and yielded >= limit:
                break

    def search_page(
        self,
        *,
        jql: str,
        max_results: int,
        fields: Optional[Iterable[str]],
        expand: Optional[Iterable[str]],
        next_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Single page fetch for enhanced JQL endpoint.
        Retries use shared _request logic.
        """
        body: Dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
        }
        if fields is not None:
            body["fields"] = fields
        if expand is not None:
            body["expand"] = expand
        if next_token:
            body["nextPageToken"] = next_token

        # Hard-code v3 endpoint (independent of api_root)
        return self._request("POST", "/rest/api/3/search/jql", json=body)

    def get_issue(
        self,
        issue_key: str,
        *,
        fields: Optional[Iterable[str]] = None,
        expand: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {}
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = ",".join(expand)
        return self._request("GET", f"{self.api_root}/issue/{issue_key}", params=params)

    def close(self) -> None:
        self.session.close()

    def get_field_display_map(
        self,
        *,
        include_reverse: bool = False,
        use_cached: bool = True
    ) -> Dict[str, str] | Tuple[Dict[str, str], Dict[str, str]]:
        """
        Return mapping of field technical ids/keys -> human display names.

        Args:
          include_reverse: if True also return reverse (displayName -> id/key)
          use_cached: future hook (no caching implemented yet)

        Jira REST: GET {api_root}/field
        Each entry commonly has: id (e.g. 'customfield_12345'), name (display label), maybe key.
        """
        path = f"{self.api_root}/field"
        data = self._request("GET", path)

        mapping: Dict[str, str] = {}
        for field in data:
            fid = field.get("id") or field.get("key")
            if not fid:
                continue
            display = field.get("name") or field.get("displayName") or fid
            mapping[fid] = display

        # Sort by human display name (case-insensitive)
        ordered = {fid: disp for fid, disp in sorted(mapping.items(), key=lambda kv: kv[1].lower())}

        if include_reverse:
            reverse = {disp: fid for fid, disp in ordered.items()}
            return ordered, reverse
        return ordered

    # ---------- Internal helpers ----------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp: Response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                if attempt <= self.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                raise JiraClientError(f"Network error after {attempt} attempts: {e}") from e

            # Rate limiting
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", self.ratelimit_sleep))
                logger.warning("Rate limited (429). Sleeping %s seconds.", retry_after)
                time.sleep(retry_after)
                continue

            if 500 <= resp.status_code < 600 and attempt <= self.max_retries:
                logger.warning("Server error %s. Retrying (attempt %s)...", resp.status_code, attempt)
                self._sleep_backoff(attempt)
                continue

            if resp.status_code >= 400:
                self._raise_for_error(resp)

            try:
                return resp.json()
            except ValueError as e:
                raise JiraClientError(f"Failed to decode JSON from {url}: {e}") from e

    def _raise_for_error(self, resp: Response) -> None:
        snippet = resp.text[:500]
        raise JiraClientError(
            f"JIRA API error {resp.status_code}: {snippet}"
        )

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self.backoff_factor ** (attempt - 1)
        logger.debug("Sleeping backoff %.2fs", delay)
        time.sleep(delay)