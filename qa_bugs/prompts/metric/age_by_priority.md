You are analyzing the Age by Priority metric.

Context JSON:
```
{{context_json}}
```

Structured markdown sections:
## Comparison
Explain relative aging across priorities (Critical, High, Medium, Low).
## Risks
Bulleted risks if High/Critical age beyond typical thresholds.
## SLA Adjustments
Bulleted proposed SLA or process adjustments per priority (bold priority name at start).
## Actions
Numbered list (3) of concrete improvements.

Return ONLY markdown.

## Instructions for analysis

### Defect SLA Guidelines
Be short and specific.
Details:
| Severity | Priority | Phase Found | Defect Age Target | Comments |
|-----------|-----------|--------------|------------------|-----------|
| Critical | P1 | Pre-production | < 3 days | Critical defects must be resolved quickly to avoid blocking development. Ensure proper root cause analysis and prioritize fixes in the sprint. |
| Critical | P1 | UAT | < 3 days | Critical defects in UAT indicate gaps in earlier testing. Focus on improving test coverage and automation in pre-production phases. |
| Critical | P1 | Production | < 1 day | Immediate action required. Critical defects in production can impact users and business operations. Establish emergency response protocols. |
| High | P2 | Pre-production | < 5 days | High-priority defects should be resolved within a sprint. Review testing processes to ensure early detection. |
| High | P2 | UAT | < 5 days | High-priority defects in UAT suggest insufficient validation in earlier phases. Strengthen regression testing. |
| High | P2 | Production | < 3 days | High-priority defects in production require quick resolution but may not need immediate hotfixes. Plan for patch releases. |
| Medium | P3 | Pre-production | < 7 days | Medium-priority defects can be addressed within the sprint cycle but should not delay critical tasks. Monitor trends to prevent accumulation. |
| Medium | P3 | UAT | < 7 days | Medium-priority defects in UAT should be resolved before the next release. Consider improving test case design. |
| Medium | P3 | Production | < 5 days | Medium-priority defects in production should be fixed in the next scheduled release. Communicate timelines to stakeholders. |
| Low | P4 | Pre-production | < 10 days | Low-priority defects can be deferred but should not be ignored. Track trends to ensure they don’t escalate. |
| Low | P4 | UAT | < 10 days | Low-priority defects in UAT can be addressed in future releases. Ensure they don’t block testing progress. |
| Low | P4 | Production | < 7 days | Low-priority defects in production can be bundled into regular maintenance updates. Communicate impact clearly to avoid unnecessary escalations. |

