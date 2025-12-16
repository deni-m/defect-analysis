You are analyzing defect rejection rate.

Input Context CSV:
```
{{context}}
```
Columns may include: rejected, total, rejection_percent, priority, severity.
Focus on:
- Overall rejection_percent and notable segments (priority/severity) with high rejection
- Possible root causes (noise, mis-triage, environment issues)

Return exactly:
1) One summary sentence.
2) A list titled **Possible Causes** (3 bullets).
3) A list titled **Recommended Actions** (2–3 bullets, each concise, starting with **Label**: ).
