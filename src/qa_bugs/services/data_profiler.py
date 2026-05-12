"""AI-powered data profiling service for semantic understanding of bug data."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class StatusProfile:
    """AI-classified status semantics."""
    all_statuses: List[str]
    open_statuses: List[str]  # In progress, analyzing, etc.
    closed_statuses: List[str]  # Done, resolved, closed, etc.
    rejected_statuses: List[str]  # Rejected, won't fix, cancelled, etc.
    confidence: float  # AI confidence score (0.0-1.0)
    method_used: str  # "llm", "fuzzy", or "config"
    warnings: List[str] = field(default_factory=list)


@dataclass
class PriorityProfile:
    """AI-classified priority semantics."""
    all_priorities: List[str]
    severity_order: List[str]  # Ordered from highest to lowest severity
    confidence: float
    method_used: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class EnvironmentProfile:
    """Environment classification and ordering."""
    all_environments: List[str]
    pipeline_order: List[str]  # Ordered from dev to prod
    production_envs: List[str]
    non_production_envs: List[str]
    confidence: float
    method_used: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class DataProfile:
    """Comprehensive data understanding for downstream processing."""
    # Data fingerprint for caching
    fingerprint: str
    
    # Field metadata
    available_fields: List[str]
    field_completeness: Dict[str, float]  # field -> non-null percentage
    
    # Date range
    date_range: Optional[Tuple[date, date]] = None
    
    # Semantic classifications (AI-generated)
    status_profile: Optional[StatusProfile] = None
    priority_profile: Optional[PriorityProfile] = None
    environment_profile: Optional[EnvironmentProfile] = None
    
    # Metric applicability
    applicable_metrics: List[str] = field(default_factory=list)
    missing_requirements: Dict[str, List[str]] = field(default_factory=dict)
    
    # Overall confidence (average of all profiles)
    overall_confidence: float = 0.0


class DataProfiler:
    """
    AI-powered service for understanding bug data semantics.
    
    Analyzes data to classify statuses, priorities, environments, and determine
    metric applicability. Uses LLM for intelligent classification with fuzzy
    matching fallback.
    """
    
    # Fuzzy matching keywords for status classification
    STATUS_KEYWORDS = {
        "open": [
            "open", "new", "todo", "to do", "funnel", "backlog",
            "analysis", "analyzing", "investigate", "investigating",
            "in progress", "progress", "working", "dev", "development",
            "ready for qa", "qa", "testing", "review", "blocked", "on hold"
        ],
        "closed": [
            "closed", "done", "resolved", "fixed", "completed",
            "released", "deployed", "verified", "ready for production"
        ],
        "rejected": [
            "rejected", "wontfix", "won't fix", "wont fix",
            "cancelled", "canceled", "duplicate", "invalid",
            "not a bug", "by design"
        ]
    }
    
    # Priority keywords for fuzzy matching
    PRIORITY_KEYWORDS = {
        "critical": ["critical", "blocker", "sev1", "p0", "highest"],
        "high": ["high", "major", "sev2", "p1"],
        "medium": ["medium", "moderate", "normal", "sev3", "p2"],
        "low": ["low", "minor", "sev4", "p3"],
        "trivial": ["trivial", "lowest", "cosmetic", "sev5", "p4"]
    }
    
    def __init__(self, llm_service: Optional["LLMService"] = None, cache_enabled: bool = True):
        """
        Initialize data profiler.
        
        Args:
            llm_service: LLMService instance for intelligent classification
            cache_enabled: Whether to cache profiles by data fingerprint
        """
        self.llm_service = llm_service
        self.llm_enabled = llm_service is not None and llm_service.enabled
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, DataProfile] = {}
    
    def profile_data(
        self,
        df: pd.DataFrame,
        config: Optional[dict] = None,
        classify_statuses: bool = True,
        classify_priorities: bool = True,
        classify_environments: bool = True
    ) -> DataProfile:
        """
        Profile bug data to understand semantics and structure.
        
        Args:
            df: Normalized DataFrame with canonical field names
            config: Optional config dict with user overrides
            classify_statuses: Whether to classify status values
            classify_priorities: Whether to classify priority values
            classify_environments: Whether to classify environment values
        
        Returns:
            DataProfile with all analysis results
        """
        # Generate fingerprint for caching
        fingerprint = self._generate_fingerprint(df)
        
        # Check cache
        if self.cache_enabled and fingerprint in self._cache:
            logger.info(f"Using cached data profile (fingerprint: {fingerprint[:8]}...)")
            return self._cache[fingerprint]
        
        logger.info("Profiling data for semantic understanding...")
        
        # Basic field analysis
        available_fields = df.columns.tolist()
        field_completeness = {
            col: float((~df[col].isna()).sum() / len(df) * 100) if len(df) > 0 else 0.0
            for col in df.columns
        }
        
        # Date range analysis
        date_range = self._analyze_date_range(df)
        
        # Semantic classification
        status_profile = None
        if classify_statuses and "status" in df.columns:
            status_profile = self._classify_statuses(df["status"], config)
        
        priority_profile = None
        if classify_priorities and "priority" in df.columns:
            priority_profile = self._classify_priorities(df["priority"], config)
        
        environment_profile = None
        if classify_environments and "environment" in df.columns:
            environment_profile = self._classify_environments(df["environment"], config)
        
        # Metric applicability analysis
        applicable_metrics, missing_requirements = self._analyze_metric_applicability(df)
        
        # Calculate overall confidence
        confidence_scores = []
        if status_profile and status_profile.confidence > 0:
            confidence_scores.append(status_profile.confidence)
        if priority_profile and priority_profile.confidence > 0:
            confidence_scores.append(priority_profile.confidence)
        if environment_profile and environment_profile.confidence > 0:
            confidence_scores.append(environment_profile.confidence)
        
        overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        
        # Build profile
        profile = DataProfile(
            fingerprint=fingerprint,
            available_fields=available_fields,
            field_completeness=field_completeness,
            date_range=date_range,
            status_profile=status_profile,
            priority_profile=priority_profile,
            environment_profile=environment_profile,
            applicable_metrics=applicable_metrics,
            missing_requirements=missing_requirements,
            overall_confidence=overall_confidence
        )
        
        # Cache result
        if self.cache_enabled:
            self._cache[fingerprint] = profile
        
        logger.info(f"Data profiling complete. Confidence: {overall_confidence:.2f}")
        
        return profile
    
    def _generate_fingerprint(self, df: pd.DataFrame) -> str:
        """Generate unique fingerprint for data (for caching)."""
        # Hash: columns + sample of first/last 10 rows + row count
        components = [
            ",".join(sorted(df.columns)),
            str(len(df)),
            str(df.head(5).values.tobytes()) if len(df) > 0 else "",
            str(df.tail(5).values.tobytes()) if len(df) > 0 else ""
        ]
        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _analyze_date_range(self, df: pd.DataFrame) -> Optional[Tuple[date, date]]:
        """Extract date range from created_at field."""
        if "created_at" not in df.columns:
            return None
        
        dates = pd.to_datetime(df["created_at"], errors="coerce").dropna()
        if len(dates) == 0:
            return None
        
        return (dates.min().date(), dates.max().date())
    
    def _classify_statuses(self, status_series: pd.Series, config: Optional[dict]) -> StatusProfile:
        """Classify status values into open/closed/rejected categories."""
        unique_statuses = status_series.dropna().unique().tolist()
        unique_statuses = [str(s) for s in unique_statuses]
        
        if not unique_statuses:
            logger.warning("No status values found in data")
            return StatusProfile(
                all_statuses=[],
                open_statuses=[],
                closed_statuses=[],
                rejected_statuses=[],
                confidence=0.0,
                method_used="none",
                warnings=["No status values found in data"]
            )
        
        logger.info(f"Classifying {len(unique_statuses)} unique statuses: {unique_statuses}")
        
        # Try LLM classification first
        if self.llm_enabled and self.llm_service:
            return self._llm_classify_statuses(unique_statuses, config)
        else:
            return self._fuzzy_classify_statuses(unique_statuses, config)
    
    def _llm_classify_statuses(self, unique_statuses: List[str], config: Optional[dict]) -> StatusProfile:
        """Use LLM to intelligently classify status values."""
        logger.info("Attempting LLM-based status classification")
        
        prompt = self._build_status_classification_prompt(unique_statuses)
        
        try:
            messages = [{"role": "user", "content": prompt}]
            ok, response_text, error = self.llm_service._chat(
                model=self.llm_service.deployment,
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
                metric_id="status_classification"
            )
            
            if not ok:
                logger.warning(f"LLM status classification failed: {error}. Falling back to fuzzy matching")
                return self._fuzzy_classify_statuses(unique_statuses, config, llm_error=error)
            
            logger.info("LLM status classification successful")
            
            # Parse response
            classification = self._parse_status_classification_response(response_text)
            
            return StatusProfile(
                all_statuses=unique_statuses,
                open_statuses=classification.get("open", []),
                closed_statuses=classification.get("closed", []),
                rejected_statuses=classification.get("rejected", []),
                confidence=0.9,  # High confidence for LLM
                method_used="llm",
                warnings=[]
            )
            
        except Exception as e:
            logger.error(f"Exception during LLM status classification: {e}", exc_info=True)
            return self._fuzzy_classify_statuses(unique_statuses, config, llm_error=str(e))
    
    def _fuzzy_classify_statuses(
        self,
        unique_statuses: List[str],
        config: Optional[dict],
        llm_error: Optional[str] = None
    ) -> StatusProfile:
        """Fallback fuzzy keyword matching for status classification."""
        logger.info("Using fuzzy keyword matching for status classification")
        
        open_statuses = []
        closed_statuses = []
        rejected_statuses = []
        unclassified = []
        
        for status in unique_statuses:
            status_lower = status.lower().strip()
            matched = False
            
            # Try rejected first (most specific)
            for keyword in self.STATUS_KEYWORDS["rejected"]:
                if keyword in status_lower:
                    rejected_statuses.append(status)
                    matched = True
                    break
            
            if matched:
                continue
            
            # Try closed
            for keyword in self.STATUS_KEYWORDS["closed"]:
                if keyword in status_lower:
                    closed_statuses.append(status)
                    matched = True
                    break
            
            if matched:
                continue
            
            # Try open
            for keyword in self.STATUS_KEYWORDS["open"]:
                if keyword in status_lower:
                    open_statuses.append(status)
                    matched = True
                    break
            
            if not matched:
                unclassified.append(status)
                # Default: if not rejected or closed, assume open
                open_statuses.append(status)
        
        warnings = []
        if llm_error:
            warnings.append(f"LLM classification failed ({llm_error}), used fuzzy matching")
        if unclassified:
            warnings.append(f"Unclassified statuses (defaulted to open): {', '.join(unclassified)}")
        
        # Lower confidence for fuzzy matching
        confidence = 0.6 if not unclassified else 0.4
        
        return StatusProfile(
            all_statuses=unique_statuses,
            open_statuses=open_statuses,
            closed_statuses=closed_statuses,
            rejected_statuses=rejected_statuses,
            confidence=confidence,
            method_used="fuzzy",
            warnings=warnings
        )
    
    def _classify_priorities(self, priority_series: pd.Series, config: Optional[dict]) -> PriorityProfile:
        """Classify and order priority values by severity."""
        unique_priorities = priority_series.dropna().unique().tolist()
        unique_priorities = [str(p) for p in unique_priorities]
        
        if not unique_priorities:
            return PriorityProfile(
                all_priorities=[],
                severity_order=[],
                confidence=0.0,
                method_used="none",
                warnings=["No priority values found in data"]
            )
        
        # Use fuzzy matching to order by severity (LLM can be added later)
        severity_map = {}
        for priority in unique_priorities:
            priority_lower = priority.lower().strip()
            
            # Match to severity level
            if any(kw in priority_lower for kw in self.PRIORITY_KEYWORDS["critical"]):
                severity_map[priority] = 0
            elif any(kw in priority_lower for kw in self.PRIORITY_KEYWORDS["high"]):
                severity_map[priority] = 1
            elif any(kw in priority_lower for kw in self.PRIORITY_KEYWORDS["medium"]):
                severity_map[priority] = 2
            elif any(kw in priority_lower for kw in self.PRIORITY_KEYWORDS["low"]):
                severity_map[priority] = 3
            elif any(kw in priority_lower for kw in self.PRIORITY_KEYWORDS["trivial"]):
                severity_map[priority] = 4
            else:
                severity_map[priority] = 999  # Unknown
        
        # Sort by severity
        severity_order = sorted(unique_priorities, key=lambda p: severity_map[p])
        
        return PriorityProfile(
            all_priorities=unique_priorities,
            severity_order=severity_order,
            confidence=0.7,
            method_used="fuzzy",
            warnings=[]
        )
    
    def _classify_environments(self, env_series: pd.Series, config: Optional[dict]) -> EnvironmentProfile:
        """Classify and order environments by pipeline stage."""
        # This is already handled by EnvironmentValueMapper
        # Just do basic analysis here
        unique_envs = env_series.dropna().unique().tolist()
        unique_envs = [str(e).upper() for e in unique_envs]
        
        if not unique_envs:
            return EnvironmentProfile(
                all_environments=[],
                pipeline_order=[],
                production_envs=[],
                non_production_envs=[],
                confidence=0.0,
                method_used="none",
                warnings=["No environment values found in data"]
            )
        
        # Simple classification by keywords
        prod_keywords = ["PROD", "PRODUCTION", "LIVE", "RELEASE"]
        production_envs = [e for e in unique_envs if any(kw in e for kw in prod_keywords)]
        non_production_envs = [e for e in unique_envs if e not in production_envs]
        
        # Order by typical pipeline stages (development → testing → pre-prod → production)
        pipeline_stages = {
            "LOCAL": 1, "DEV": 2, "DEVELOPMENT": 2,
            "TEST": 3, "TESTING": 3, "QA": 4,
            "STAGE": 5, "STAGING": 5, "STG": 5, "UAT": 5, "PERF": 5,
            "PROD": 6, "PRODUCTION": 6, "LIVE": 6, "RELEASE": 6
        }
        
        def get_env_order(env: str) -> int:
            """Get pipeline order for environment."""
            env_upper = env.upper()
            # Check exact match first
            if env_upper in pipeline_stages:
                return pipeline_stages[env_upper]
            # Check if environment contains any keyword
            for keyword, order in pipeline_stages.items():
                if keyword in env_upper:
                    return order
            # Unknown environments go after testing but before staging
            return 4.5
        
        # Sort all environments by pipeline order
        pipeline_order = sorted(unique_envs, key=get_env_order)
        
        return EnvironmentProfile(
            all_environments=unique_envs,
            pipeline_order=pipeline_order,
            production_envs=production_envs,
            non_production_envs=non_production_envs,
            confidence=0.7,
            method_used="fuzzy",
            warnings=[]
        )
    
    def _analyze_metric_applicability(self, df: pd.DataFrame) -> Tuple[List[str], Dict[str, List[str]]]:
        """Determine which metrics can run on this data."""
        from qa_bugs.metrics import METRICS
        
        applicable = []
        missing = {}
        
        for metric_id, metric_cls in METRICS.items():
            required_fields = getattr(metric_cls, "requires", set())
            
            if not required_fields:
                applicable.append(metric_id)
                continue
            
            missing_fields = [f for f in required_fields if f not in df.columns]
            
            if not missing_fields:
                applicable.append(metric_id)
            else:
                missing[metric_id] = missing_fields
        
        return applicable, missing
    
    def _build_status_classification_prompt(self, unique_statuses: List[str]) -> str:
        """Build prompt for LLM status classification."""
        statuses_str = "\n".join([f"  - {s}" for s in unique_statuses])
        
        return f"""You are a bug tracking system expert. Classify the following bug status values into three categories:

**Categories:**
1. **Open** - Bug is not yet resolved (in progress, analyzing, under development, etc.)
2. **Closed** - Bug has been resolved and completed (done, fixed, resolved, released, etc.)
3. **Rejected** - Bug was rejected or won't be fixed (rejected, won't fix, cancelled, duplicate, invalid, etc.)

**Classification Rules:**
- Be conservative: if unsure, prefer "Open"
- Consider workflow: "Ready for QA" is still Open, "Done" is Closed
- Common patterns: "In Progress" → Open, "Resolved" → Closed, "Won't Fix" → Rejected

**Status Values to Classify:**
{statuses_str}

**Response Format:**
Return ONLY a YAML mapping in this exact format (no markdown fences, no explanations):

open:
  - Status1
  - Status2
closed:
  - Status3
rejected:
  - Status4

Use EXACT original status names (case-sensitive) in your response.

Your response (YAML only):"""
    
    def _parse_status_classification_response(self, response: str) -> Dict[str, List[str]]:
        """Parse YAML classification from LLM response."""
        import yaml
        
        # Extract YAML from potential markdown fences
        if "```yaml" in response:
            response = response.split("```yaml")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        # Parse YAML
        data = yaml.safe_load(response)
        
        return {
            "open": data.get("open") or [],
            "closed": data.get("closed") or [],
            "rejected": data.get("rejected") or [],
        }
    
    def format_profile_summary(self, profile: DataProfile) -> str:
        """Format profile as user-friendly summary."""
        lines = [f"✓ Data Profile (confidence: {profile.overall_confidence:.0%})\n"]
        
        # Date range
        if profile.date_range:
            lines.append(f"**Date Range:** {profile.date_range[0]} to {profile.date_range[1]}")
        
        # Status classification
        if profile.status_profile:
            sp = profile.status_profile
            lines.append(f"\n**Status Classification** ({sp.method_used}, confidence: {sp.confidence:.0%}):")
            lines.append(f"  • Open: {', '.join(sp.open_statuses) if sp.open_statuses else 'none'}")
            lines.append(f"  • Closed: {', '.join(sp.closed_statuses) if sp.closed_statuses else 'none'}")
            lines.append(f"  • Rejected: {', '.join(sp.rejected_statuses) if sp.rejected_statuses else 'none'}")
            
            if sp.warnings:
                lines.append(f"  ⚠ Warnings:")
                for warning in sp.warnings:
                    lines.append(f"    - {warning}")
        
        # Priority classification
        if profile.priority_profile:
            pp = profile.priority_profile
            lines.append(f"\n**Priority Order** ({pp.method_used}):")
            lines.append(f"  {' > '.join(pp.severity_order)}")
        
        # Environment classification
        if profile.environment_profile:
            ep = profile.environment_profile
            lines.append(f"\n**Environments** ({ep.method_used}):")
            lines.append(f"  • Production: {', '.join(ep.production_envs) if ep.production_envs else 'none'}")
            lines.append(f"  • Non-Production: {', '.join(ep.non_production_envs) if ep.non_production_envs else 'none'}")
        
        # Metric applicability
        if profile.missing_requirements:
            lines.append(f"\n**⚠ Metrics with Missing Data:**")
            for metric_id, fields in profile.missing_requirements.items():
                lines.append(f"  • {metric_id}: missing {', '.join(fields)}")
        
        return "\n".join(lines)
