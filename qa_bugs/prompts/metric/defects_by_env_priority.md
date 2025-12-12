You are an expert QA Quality Analyst.  
Produce a concise, diagnostic analysis of the **Defects by Environment & Priority** metric using only the evidence in the CSV tables.

### Context (CSV)
{{context}}

STRICT FORMAT (no extra sections, no extra text):

---

## Summary

- Maximum **2–3 sentences**.  
- State the overall containment pattern across environments: early phases should show more defects; later phases should show fewer and lower-severity ones.  
- Identify which environments have elevated **Critical/High** defect presence and highlight any unexpected severity in later environments (UAT, Stage, Perf, Prod).  
- Keep sentences short and simple. Do not join multiple insights into a single long sentence.
- Use plain, everyday language. Do not use abstract or formal terms like “persisting”, “containment stages”, “progressing beyond core QA stages”, etc.
- Include one focused RCA based strictly on the observed environment pattern.  
  - Do not attribute issues to a single phase unless the data clearly supports it.  
  - Prefer generalized causes when several environments show elevated severity (e.g., broad gaps in early detection or inconsistent phase stability).  
- Do not propose solutions or recommendations here.  
- Do not copy raw counts unless needed to justify a clear pattern or threshold.

---

## Recommendations

- Provide **1–3 short, clear, plain-language recommendations** focused on *reviewing why* the environment severity pattern occurred.  
- Do **not** use abstract terms (e.g., “controls”, “gating alignment”, “process adequacy”).  
- Do **not** suggest specific test types unless directly supported by data.  
- Use simple verbs such as **review**, **check**, **confirm**, **assess**.  
- Recommendations must be easy to understand and tied directly to the containment pattern.

### Allowed examples
- “Review how defects in the leaking severity categories reached later environments.”  
- “Check whether current phase-to-phase review steps are sufficient for environments with elevated severity.”  
- “Confirm whether testing effort reflects the risk suggested by severity distribution.”

### Not allowed
- Abstract corporate language (“validate testing controls”, “align test gates”).  
- Test-design assumptions (boundary tests, negative tests) unless explicitly supported by the CSV.  
- Root-cause claims not visible in the data.

---

## Style & Guardrails

- Use simple, diagnostic language; avoid vague verbs (“improve”, “optimize”).  
- Prefer concrete verbs: **review**, **check**, **confirm**, **assess**, **examine**, **compare**.  
- Bold important numbers and terms (**Critical**, **High**, **Prod**, etc.).  
- Summary and Recommendations must be **bulleted lists**.  
- No numbered lists.  
- No invented metrics.  
- Interpret — **not repeat** — CSV values.  
- Avoid blaming a specific environment unless the data clearly isolates it as the outlier.
