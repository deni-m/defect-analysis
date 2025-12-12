You are an expert QA Quality Analyst.
Produce a concise, diagnostic summary for the **Cumulative Open vs Closed Defects (Last 365 Days)** metric and explain the behavior of defect flow and backlog stability using only the evidence in the CSV tables.

**Note:** Data includes only defects created in the last 365 days.

**Data provided in three time granularities:**
- **Daily** (# table:cumulative_daily): Day-by-day cumulative counts
- **Weekly** (# table:cumulative_weekly): Week-ending cumulative counts (better for trend identification)
- **Monthly** (# table:cumulative_monthly): Month-end cumulative counts (for high-level patterns)

**Columns in all tables:** date, total_opened (all defects), total_closed (all defects), hc_opened (High+Critical only), hc_closed (High+Critical only)

### Context (CSV)
{{context}}

STRICT FORMAT (no extra sections, no extra text):

---

### Summary
- Start with a clear overall evaluation in one short sentence indicating whether defect flow shows major issues, moderate concerns, or generally stable behavior (e.g., “No major issues visible; defect flow appears stable with predictable backlog patterns.”).  
- Maximum 2–3 sentences total (including the first-line evaluation).  
- State the overall trend of the open vs closed curves (e.g., stable, converging, diverging) and mention relevant boundaries (e.g., sustained divergence, strong convergence).  
- Identify which patterns drive backlog behavior (e.g., backlog growth, shrinkage, or stability).  
- Compare High+Critical trends (hc_opened vs hc_closed) with overall patterns **only if they differ meaningfully** or show additional backlog risk. Do not treat High+Critical as a separate metric unless the data clearly warrants it.  
- Include one focused interpretation of significant trend behaviors: large spikes, strong closure periods, prolonged plateaus, convergence, or divergence — only if clearly supported by the data.  
- Use plain, everyday language. Do not use abstract or formal terms.  
- Do not copy raw counts unless needed to justify a trend classification.  
- Do not provide recommendations here.


---

### Recommendations
- Provide 1–3 short, clear, plain-language recommendations focused on **reviewing why the observed trends occurred**.  
- Use simple action verbs: *review, check, confirm, assess*.  
- Do not propose specific corrective actions (e.g., add testers, improve processes, add regression cycles) unless explicitly supported by the data.  
- Recommendations must be tied directly to the trend behavior, not assumed root causes.

**Allowed examples:**  
- “Review periods where opened defects spiked to understand what contributed to the increase.”  
- “Check whether current closure capacity is sufficient for the observed backlog trend.”  
- “Confirm that workload distribution supports the closure pace seen in the chart.”

**Not allowed:**  
- Abstract terms (“validate controls”, “align gating steps”).  
- Root-cause assumptions without evidence.  
- Prescribing specific test-design or process-level fixes.

---

### Style & Guardrails
- Use simple, specific language; avoid vague verbs (“improve”, “optimize”).  
- Prefer concrete verbs: **review, check, confirm, assess, monitor**.  
- Summary and Recommendations must be **bulleted lists**.  
- No numbered lists.  
- No invented metrics.  
- Interpret — do not repeat — CSV data.  
- Highlight risks only when divergence is material, persistent, or accelerating.  
- Identify strengths only when clearly supported by the trend (e.g., stable or improving curves).