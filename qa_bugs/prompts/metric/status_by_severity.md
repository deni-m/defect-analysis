You are analyzing defect status distribution by severity.

Use only aggregated data from the CSV below.

### Status classification
Open statuses = {Funnel, Analysis, To Do, In Progress, Blocked / On Hold, Ready for Production}
Closed statuses = {Done, Cancelled}

### Important rules
1. Ignore rows where severity = ST or severity = TBD. These are not real severities.
2. For each severity, compute:
   - open_count = sum(count where status ∈ Open statuses)
   - closed_count = sum(count where status ∈ Closed statuses)
   Cancelled counts as CLOSED, not stagnation.

### Your goals:
1. Identify which severities dominate the open backlog.
2. Compare closure performance across severities.
3. Detect any high-severity stagnation or bottlenecks.

### Output exactly:
1) A short summary (≤50 words).
2) A **Risks** section (2–3 bullets).
3) An **Actions** section (3 bullets, each starting with a verb).

### Data (severity, status, count):
{{context}}
