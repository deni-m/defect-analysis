# AI Data Analysis & Metric Recommendations Layer

## Overview

This document tracks the implementation of an intelligent data analysis layer that provides:
- Automated data quality assessment
- Smart metric recommendations based on actual data characteristics
- Anomaly detection and insights generation
- Intelligent filtering and segmentation suggestions
- Explainability and user education
- Actionable recommendations for process improvement

## 🎯 MVP Scope

We're implementing a **Minimum Viable Product (MVP)** focused on the 5 most impactful features:

### MVP Features (Priority Order)

1. **Data Quality Assessment** - Foundation for reliable analysis
   - Field completeness analysis
   - Critical field validation
   - Quality scoring and warnings

2. **Metric Applicability Intelligence** - Prevent wasted effort
   - Technical validation (required fields, data types)
   - Statistical validation (sample size, variance)
   - Clear can/cannot run decisions

3. **Smart Metric Recommendations** - Core value proposition
   - Scoring system (0-100 per metric)
   - Top 3-5 recommended metrics
   - Clear explanations for recommendations

4. **Pattern Recognition** - Automatic insights
   - Simple pattern detection (high-frequency values, temporal trends)
   - Outlier identification
   - Actionable pattern summaries

5. **Actionable Recommendations** - Drive improvements
   - Data quality improvement suggestions
   - Process improvement recommendations
   - Metric strategy guidance

**MVP Goal:** Complete end-to-end flow from data upload → quality check → metric recommendations → insights → actions

**Out of Scope for MVP:** Personalization, what-if scenarios, advanced ML, cross-project learning

## Implementation Status

### Phase 0: Data Profiler ✅ COMPLETE
**Status:** Production-ready (Completed: January 2026)

Core functionality for AI-powered semantic classification of bug data.

- [x] DataProfiler service with LLM + fuzzy classification
- [x] Status, priority, environment classification
- [x] Confidence scoring (0.0-1.0)
- [x] Fingerprint-based caching
- [x] Integration into AnalysisService workflow
- [x] Auto-apply high-confidence classifications to configs
- [x] Profile-aware metrics (status_by_severity, defect_age)
- [x] CLI flag (--auto-classify) and config support
- [x] HTML report integration with styled profile section
- [x] Test coverage (4 tests passing)
- [x] Documentation in README
- [x] **Streamlit UI display with 4 tabs** (Status/Priority/Environment/Summary) - *Added Jan 22, 2026*
- [x] **UI toggle for auto-classification** - *Added Jan 22, 2026*
- [x] **Fixed environment pipeline ordering** (QA → STAGE → PROD) - *Fixed Jan 22, 2026*

**Files:**
- `src/qa_bugs/services/data_profiler.py`
- `tests/test_data_profiler.py`
- `src/qa_bugs/ui/components/results_display.py` - Display component
- `src/qa_bugs/ui/app.py` - UI toggle integration

---

## 🚀 MVP IMPLEMENTATION

**Status:** 🟡 Not Started  
**Estimated Effort:** 2-3 days  
**Test Coverage Target:** 90%

### Implementation Tasks

- [ ] Create `DataQualityAnalyzer` service class
- [ ] Field completeness scoring (% non-null per field)
- [ ] Critical field validation (ID, status, created_date required)
- [ ] Quality score calculation (0-100)
- [ ] Quality level classification (HIGH/ADEQUATE/LOW/INCOMPLETE)
- [ ] Warning generation for quality issues
- [ ] Unit tests (test_data_quality_analyzer.py)

### Data Models

```python
@dataclass
class DataQualityProfile:
    """Simple data quality assessment"""
    field_completeness: dict[str, float]  # field -> % complete (0-100)
    critical_fields_ok: bool  # All critical fields present?
    quality_score: float  # Overall score 0-100
    quality_level: str  # HIGH, ADEQUATE, LOW, INCOMPLETE
    warnings: list[str]  # Human-readable warnings
    sample_size: int  # Number of records analyzed
```

### Quality Levels (MVP - Keep Simple)

- **HIGH_QUALITY** (90-100): All critical fields >95% complete
- **ADEQUATE_QUALITY** (70-89): Critical fields >80% complete
- **LOW_QUALITY** (50-69): Critical fields 60-80% complete
- **INCOMPLETE_DATA** (<50): Missing critical fields, warn user

### Files to Create

- `src/qa_bugs/services/data_quality_analyzer.py` - Main service
- `tests/test_data_quality_analyzer.py` - Unit tests (5+ tests)

### Test Cases

1. `test_perfect_quality()` - All fields 100% complete
2. `test_missing_critical_field()` - ID or status missing
3. `test_partial_completeness()` - 80% complete scenario
4. `test_quality_score_calculation()` - Score formula validation
5. `test_warning_generation()` - Warnings for incomplete data
- [ ] Warning templates (e.g., "20% of bugs missing priority - consider cleanup")
- [ ] Warning display in UI with suggested actions
- [ ] Warning suppression mechanism (user can mark as acknowledged)

---

## Phase 3: Metric Applicability Intelligence 🔄 PLANNED

### 3.1 Technical Validation
**Priority:** High  
**Estimated Effort:** 3-4 days

Automatically validate if metrics can run with current data.

- [ ] Required field checker (metric -> required fields)
- [ ] Data type validation (e.g., dates are parseable)
- [ ] Cardinality checks (e.g., status has >1 unique value)
- [ ] Dep2: Metric Applicability Intelligence 🔄 PLANNED
**MVP Priority:** #2 - Prevent wasted effort

**Status:** 🟡 Not Started  
**Estimated Effort:** 2-3 days  
**Test Coverage Target:** 90%

### Implementation Tasks

- [ ] Create `MetricValidator` service class
- [ ] Define required fields per metric (simple dictionary)
- [ ] Technical validation (fields exist, correct types)
- [ ] Statistical validation (sample size, variance)
- [ ] Validation result with can_run flag
- [ ] Unit tests (test_metric_validator.py)

### Data Models

```python
@dataclass
class ValidationResult:
    """Simple metric validation result"""
    metric_id: str
    can_run: bool  # True if metric can execute
    confidence: float  # 0-100: how meaningful results will be
    status: str  # OK, WARNING, ERROR
    issues: list[str]  # What's wrong (if any)
    suggestions: list[str]  # How to fix (if can't run)

# Simple validation rules per metric
METRIC_REQUIREMENTS = {
    "defect_age": {
        "required_fields": ["id", "created_date", "status"],
        "min_sample_size": 10,
        "needs_date_range": True
    },
    "status_by_severity": {
        "required_fields": ["id", "status", "severity"],
        "min_sample_size": 5,
        "min_unique_statuses": 2
    },
    "leakage_rate": {
        "required_fields": ["id", "environment"],
        "min_environments": 2,  # Need test + prod
        "min_sample_size": 20
    }
}
```

### Validation Logic (Keep Simple for MVP)

1. **Technical Check**: Required fields present?
2. **Sample Size Check**: Enough data? (>10 records minimum)
3. **Variance Check**: Data varied enough? (e.g., not all same status)
4. **Special Requirements**: Metric-specific rules (e.g., leakage needs 2+ envs)

### Files to Create

- `src/qa_bugs/services/metric_validator.py` - Main service
- `tests/test_metric_validator.py` - Unit tests (6+ tests)

### Test 3: Smart Metric Recommendations 🔄 PLANNED
**MVP Priority:** #3 - Core value proposition

**Status:** 🟡 Not Started  
**Estimated Effort:** 2-3 days  
**Test Coverage Target:** 90%

### Implementation Tasks

- [ ] Create `MetricRecommender` service class
- [ ] Simple scoring algorithm (validation result + data characteristics)
- [ ] Top N recommendations (return best 3-5 metrics)
- [ ] Clear explanations for scores
- [ ] Unit tests (test_metric_recommender.py)

### Data Models

```python
@dataclass
class MetricRecommendation:
    """Simple metric recommendation with score"""
    metric_id: str
    score: float  # 0-100
    recommendation_level: str  # HIGHLY_RECOMMENDED, RECOMMENDED, OPTIONAL
    explanation: str  # Why this score?
    reasoning: list[str]  # Bullet points explaining score
    can_run: bool  # From validation

# Simple scoring formula for MVP
def calculate_score(validation: ValidationResult, data_stats: dict) -> float:
    score = 0.0
    
    # Base score from validation (60 points max)
    if validation.can_run:
        score += 40  # Can run = base 40
        score += min(validation.confidence / 5, 20)  # Confidence adds up to 20
    
    # Data characteristics bonus (40 points max)
    # - Multiple environments? +10 for env metrics
    # - High bug count? +10 for statistical metrics
    # - Long time range? +10 for trend metrics
    # - Priority data? +10 for priority metrics
    
    return min(score, 100)
```

### Recommendation Levels (MVP - Simple Thresholds)

- **HIGHLY_RECOMMENDED** (80-100): ⭐⭐⭐ Run this first
- **RECOMMENDED** (60-79): ⭐⭐ Useful insights
- **OPTIONAL** (40-59): ⭐ Run if interested
- **NOT_RECOMMENDED** (<40): Skip for now

### Files to Create

- `src/qa_bugs/services/metric_recommender.py` - Main service
- `tests/test_metric_recommender.py` - Unit tests (5+ tests)

### Test Cases

1. `test_recommend_top_metrics()` - Returns top 3-5 metrics
2. `test_scoring_formula()` - Score calculation correct
3. `test_high_quality_data_boosts_score()` - Good data = higher scores
4. `test_missing_fields_lower_score()` - Missing data = lower scores
5. `test_explanation_generation()` - Clear reasoning provided

---

## Phase 5: Data Insights & Anomaly Detection 🔄 PLANNED

### 5.1 Pattern Recognition
**Priority:** Medium  
**Estimated Effort:** 5-7 days

Automatically detect interesting patterns in data.

- [ ] Clustering analysis (bug similarity groups)
- [ ] Periodic pattern detection (weekly/monthly cycles)
- [ ] Correlation discovery (e.g., certain components have higher severity)
- [ ] Trend identification (improving, degrading, stable)

**Pattern Types:**
```python
@dataclass
class DetectedPattern:
    pattern_type: str  # cluster, cycle, correlation, trend
    description: str  # "80% of critical bugs are in payment module"
    confidence: float
    impact: str  # HIGH, MEDIUM, LOW
    recommendation: str  # suggested action
```

**Examples:**
- "Friday deployments have 3× higher bug rates than other days"
- "Environment 'STAGING' has 60% of all High priority bugs"
- "Averag4: Pattern Recognition 🔄 PLANNED
**MVP Priority:** #4 - Automatic insights

**Status:** 🟡 Not Started  
**Estimated Effort:** 2-3 days  
**Test Coverage Target:** 85%

### Implementation Tasks

- [ ] Create `PatternDetector` service class
- [ ] Simple pattern detection (high-frequency values, outliers)
- [ ] Temporal trend detection (improving/degrading)
- [ ] Pattern descriptions in plain English
- [ ] Unit tests (test_pattern_detector.py)

### Data Models

```python
@dataclass
class DetectedPattern:
    """Simple pattern detection result"""
    pattern_type: str  # concentration, outlier, trend
    title: str  # Short summary
    description: str  # Plain English explanation
    impact_level: str  # HIGH, MEDIUM, LOW
    affected_count: int  # How many bugs affected
    evidence: dict  # Supporting data

# MVP Pattern Types (Keep Simple)
# 1. CONCENTRATION: "60% of bugs are in PROD environment"
# 2. OUTLIER: "Bug #123 is 180 days old (10x average)"
# 3. TREND: "Average age decreased 30% in last 30 days"
```

### Simple Pattern Detection (MVP - No ML Required)

1. **Concentration Patterns**: Find high-frequency values
   - If any value represents >50% of data → flag it
   - Example: "80% of bugs are Priority=Low"

2. **Outlier Detection**: Simple statistical outliers
   - Use IQR method: value > Q3 + 1.5×IQR
   - Example: "3 bugs are >90 days old (avg is 15)"

3. **Trend Detection**: Compare time periods
   - Split data in half, compare averages
   - Example: "Bug creation rate up 25% in last 2 weeks"

### Files to Create

- `src/qa_bugs/services/pattern_detector.py` - Main service
- `tests/test_pattern_detector.py` - Unit tests (5+ tests)

### Test Cases

1. `test_detect_concentration()` - Finds 80% in one category
2. `test_detect_outliers()` - Identifies statistical outliers
3. `test_detect_trend()` - Compares time periods
4. `test_no_patterns()` - Handles uniform data gracefully
5. `test_pattern_description()` - Generates readable text
- [ ] Bug cohorts (by creation week/month)
- [ ] Survival analysis (how long bugs remain open)
- [ ] Cohort comparison (Q4 2025 bugs vs Q1 2026 bugs)
- [ ] Segment performance (priority groups, environment groups)

---

## Phase 7: Explainability & Education 🔄 PLANNED

### 7.1 Plain English Explanations
**Priority:** High  
**Estimated Effort:** 3-4 days

Make metrics understandable to non-technical users.

- [ ] Met5: Actionable Recommendations 🔄 PLANNED
**MVP Priority:** #5 - Drive improvements

**Status:** 🟡 Not Started  
**Estimated Effort:** 2 days  
**Test Coverage Target:** 85%

### Implementation Tasks

- [ ] Create `InsightGenerator` service class
- [ ] Generate data quality recommendations
- [ ] Generate process improvement recommendations
- [ ] Format recommendations with priority levels
- [ ] Unit tests (test_insight_generator.py)

### Data Models

```python
@dataclass
class Insight:
    """Simple actionable recommendation"""
    category: str  # data_quality, process, metric_strategy
    priority: str  # HIGH, MEDIUM, LOW
    title: str  # Short headline
    description: str  # Detailed explanation
    action_items: list[str]  # Specific steps to take
    impact: str  # What improves if action taken

# MVP Recommendation Categories
# 1. DATA_QUALITY: Fix missing fields, standardize values
# 2. PROCESS: Address patterns (old bugs, high concentration)
# 3. METRIC_STRATEGY: Which metrics to run regularly
```

### Simple Recommendation Logic (MVP - Rule-Based)

**Data Quality Recommendations:**
- Missing critical field → "Add [field] to enable [metrics]"
- <80% completeness → "Improve data completeness to get better insights"
- Inconsistent values → "Standardize [field] values (found: X, Y, Z)"

**Process Recommendations:**
- >50% bugs in one category → "Investigate why [category] has most bugs"
- Bugs >90 days old → "Review and close old bugs"
- Trend degrading → "Bug age increasing - consider more resources"

**Metric Strategy:**
- Based on recommender scores → "Focus on these 3 metrics weekly"
- Data characteristics → "Your data supports [metrics]"

### Files to Create

- `src/qa_bugs/services/insight_generator.py` - Main service
- `tests/test_insight_generator.py` - Unit tests (5+ tests)

### Test Cases

1. `test_data_quality_recommendations()` - Suggests field additions
2. `test_process_recommendations()` - Flags concentration patterns
3. `test_metric_strategy()` - Recommends metric tracking plan
4. `test_prioritization()` - HIGH/MEDIUM/LOW assigned correctly
5. `test_no_recommendations()` - Handles perfect data gracefully

---

## 🔄 POST-MVP FEATURES (Future Phases)

These features are deferred until MVP is complete and validated:

- **Persona-based Recommendations**: Tailor to developer/QA/manager roles
- **What-If Scenarios**: Interactive exploration of changes
- **Advanced ML Patterns**: Clustering, predictive analytics
- **Cross-Project Learning**: Pattern library, benchmarking
- **Intelligent Filtering**: Auto-suggest filters and segments
- **Interactive Glossary**: Tooltips and educational content
- **Feedback Loops**: Learn from user interactions

## Phase 10: Continuous Learning 🔄 PLANNED

### 10.1 Feedback Loops
**Priority:** Medium  
**Estimated Effort:** 3-4 days

Learn from user interactions to improve recommendations.

- [ ] User feedback collection (thumbs up/down on recommendations)
- [ ] Implicit feedback (which metrics user runs, which filters used)
- [ ] A/B testing for recommendation algorithms
- [🏗️ MVP  recommendation: str
    
@dataclass
class Insight:
    category: str  # quality, process, trend, anomaly
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    title: str
    description: str
    evidence: dict  # Supporting data
    recommendations: list[str]
    
@dataclass
class UserContext:
    persona: str  # developer, qa_lead, manager, executive
    goals: list[str]  # quality_improvement, reporting, etc.
    project_phase: str  # startup, growth, mature
    preferences: dict  # Learned preferences
```

## Dependencies

### Current
- ✅ LLM service (Azure OpenAI or OpenAI)
- ✅ DataProfiler (status, priority, environment classification)
- ✅ pandas for data manipulation
- ✅ plotly for visualization

### Required for Full Implementation
- [ ] scikit-learn (clustering, anomaly detection, prediction)
- [ ] scipy (statistical tests, distributions)
- [ ] statsmodels (time series analysis, forecasting)
- [ ] numpy (numerical operations)
- [ ] Optional: prophet or similar for time series forecasting
- [ ] Optional: shap or similar for ML explainability

## Testing Strategy

### Unit Tests
- [ ] Data quality analysis functions
- [ ] Metric scoring algorithms
- [ ] Pattern detection logic
- [ ] Recommendation generation
- [ ] Persona detection

### Integration Tests
- [ ] End-to-end recommendation flow
- [ ] UI integration with recommendation engine
- [ ] Feedback loop functionality
- [ ] Cross-service communication

### Performance Tests
- [ ] Large dataset handling (>10k bugs)
- [ ] Recommendation response time (<2 seconds)
- [ ] Pattern detection efficiency
- [ ] Caching effectiveness

## MVP Success Criteria

### Functional Requirements
- ✅ All 5 phases implemented and tested
- ✅ 90%+ test coverage across all new services
- ✅ Recommendations display in HTML report
- ✅ CLI flag to enable/disable recommendations
- ✅ Works with sample_bugs.csv

### Quality Requirements
- Response time: <5 seconds total for all 5 phases
- Accuracy: Recommendations make sense for sample data
- Robustness: Handles edge cases (empty data, missing fields)
- Clarity: All explanations readable by non-technical users

### User Experience
- Clear visual section in report for recommendations
- Top 3-5 metrics highlighted with scores
- Patterns and insights easy to understand
- Action items specific and achievable

## Implementation Timeline

### Sprint 1 (Days 1-3)
- Phase 1: Data Quality Analyzer + tests
- Phase 2: Metric Validator + tests

### Sprint 2 (Days 4-6)
- Phase 3: Metric Recommender + tests
- Phase 4: Pattern Detector + tests

### Sprint 3 (Days 7-8)
- Phase 5: Insight Generator + tests
- Integration into AnalysisService

### Sprint 4 (Days 9-10)
- HTML report updates
- Integration tests
- Documentation

**Total Estimated Time:** 10 working days

## Post-MVP Roadmap

After MVP validation, consider:
1. **Streamlit Integration** - Interactive recommendations UI
2. **Advanced Patterns** - ML-based clustering, predictions
3. **Personalization** - User personas and preferences
4. **Feedback Loops** - Learn from user interactions
5. **Cross-Project Insights** - Benchmark against other projects

---

## 📝 Implementation Log

### January 22, 2026
- ✅ **Phase 0 Enhancement**: Added Data Profiler display to Streamlit UI
  - Created 4-tab interface (Status/Priority/Environment/Summary)
  - Added UI toggle for auto-classification in sidebar
  - Fixed environment pipeline ordering (QA → STAGE → PROD)
  - Files modified: `results_display.py`, `app.py`, `data_profiler.py`

### Next Session
- 🎯 **Phase 1**: Implement Data Quality Analyzer service
- 🎯 **Phase 2**: Implement Metric Validator service
- 🎯 **Phase 3**: Implement Metric Recommender service

---

**Last Updated:** January 22, 2026 16:30  
**Current Status:** 🎯 Phase 0 Complete ✅ | Ready for MVP Phase 1  
**Next Step:** Phase 1 - Data Quality Analyzer implementation
        self, 
        df: pd.DataFrame,
        quality_profile: DataQualityProfile,
   MVP Testing Strategy

### Unit Tests (90% coverage target)

**Phase 1 Tests** (`tests/test_data_quality_analyzer.py`):
- [x] test_perfect_quality - All fields 100% complete
- [ ] test_missing_critical_field - ID/status missing
- [ ] test_partial_completeness - 80% scenario
- [ ] test_quality_score_calculation - Formula validation
- [ ] test_warning_generation - Incomplete data warnings

**Phase 2 Tests** (`tests/test_metric_validator.py`):
- [ ] test_validation_all_ok - Perfect data
- [ ] test_missing_required_field - Field missing
- [ ] test_insufficient_sample_size - <10 records
- [ ] test_no_variance - All same status
- [ ] test_leakage_needs_multiple_envs - 1 env → can't run
- [ ] test_validation_suggestions - Proper suggestions

**Phase 3 Tests** (`tests/test_metric_recommender.py`):
- [ ] test_recommend_top_metrics - Returns top 3-5
- [ ] test_scoring_formula - Score calculation
- [ ] test_high_quality_boosts_score - Good data = higher
- [ ] test_missing_fields_lower_score - Missing = lower
- [ ] test_explanation_generation - Clear reasoning

**Phase 4 Tests** (`tests/test_pattern_detector.py`):
- [ ] test_detect_concentration - 80% in one category
- [ ] test_detect_outliers - Statistical outliers
- [ ] test_detect_trend - Time period comparison
- [ ] test_no_patterns - Uniform data handling
- [ ] test_pattern_description - Readable text

**Phase 5 Tests** (`tests/test_insight_generator.py`):
- [ ] test_data_quality_recommendations - Field additions
- [ ] test_process_recommendations - Concentration flags
- [ ] test_metric_strategy - Tracking plan
- [ ] test_prioritization - HIGH/MEDIUM/LOW
- [ ] test_no_recommendations - Perfect data

### Integration Tests
- [ ] End-to-end: CSV → quality → validate → recommend → patterns → insights → report
- [ ] Test with sample_bugs.csv
- [ ] Test with empty/minimal data
- [ ] Test with high-quality complete data

### Performance Goals (MVP)
- Quality analysis: <1 second for 1000 bugs
- Validation: <1 second for all metrics
- Recommendations: <2 seconds total
- Pattern detection: <2 seconds for 1000 bugs
- Insight generation: <1 secondatterns()
   ↓ (list[DetectedPattern])
7. InsightGenerator.generate_insights()
   ↓ (list[ (Already Available)
- ✅ pandas - Data manipulation
- ✅ numpy - Numerical operations (via pandas)
- ✅ plotly - Visualization
- ✅ LLM service - Optional, for DataProfiler

### MVP Requirements (Minimal New Dependencies)
- ✅ **NO new dependencies needed!** 
- All MVP features can be implemented with pandas + numpy
- Simple statistical methods: mean, median, IQR, percentiles
- Pattern detection via value_counts(), groupby(), basic aggregations

### Post-MVP (If Needed Later)
- [ ] scikit-learn - Advanced clustering, ML-based anomaly detection
- [ ] scipy - Advanced statistical tests
- [ ] statsmodels - Time series forecasting
        quality_analyzer = DataQualityAnalyzer()
        quality_profile = quality_analyzer.analyze(df)
        
        # NEW: Step 3 - Validate and recommend metrics
        validator = MetricValidator()
        validations = validator.validate_all_metrics(df)
        
        recommender = MetricRecommender(validator, quality_analyzer)
        recommendations = recommender.recommend_metrics(df, top_n=5)
        
        # NEW: Step 4 - Compute metrics (use recommendations)
        metrics_to_run = self._select_metrics(config, recommendations)
        metric_results = self._compute_metrics(df, metrics_to_run, config)
        
        # NEW: Step 5 - Detect patterns
        pattern_detector = PatternDetector()
        patterns = pattern_detector.detect_patterns(df)
        
        # NEW: Step 6 - Generate insights
        insight_generator = InsightGenerator(quality_analyzer, pattern_detector)
        insights = insight_generator.generate_insights(
            df, quality_profile, patterns, recommendations
        )
        
        # Add to result
        return AnalysisResult(
            ...,
            quality_profile=quality_profile,
            recommendations=recommendations,
            patterns=patterns,
            insights=insights
        )