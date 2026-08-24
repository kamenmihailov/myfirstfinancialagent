# Research Workflow

Use this workflow whenever the user provides a topic and asks for a research report.

---

## Step 1 — Intake

Receive the topic from the user. It can be a keyword, a question, or a sentence. No action yet — proceed to Step 2.

---

## Step 2 — Clarifying Questions

Before researching anything, ask the user these questions in a single message (do not split across multiple messages):

1. **Scope** — How broad or narrow should the research be? (e.g., global overview, one country, one industry, one product category)
2. **Audience** — Who is this report for? (e.g., general readers, technical professionals, business executives, your own reference)
3. **Specific angle** — Are there particular questions you want answered, or aspects you care most about?
4. **Recency** — How fresh must the data be? (e.g., last 6 months, last 2 years, any timeframe)
5. **Length** — Brief (1 page / ~5 sections), Standard (2–3 pages), or Deep-dive (comprehensive)?

Wait for the user's answers before doing anything else.

---

## Step 3 — Research Outline

Based on the user's answers, propose a research outline in a single message. Include:

- **Topic summary**: one sentence restating the topic and confirmed scope
- **Proposed sections**: list each section name with a one-sentence description of what it will cover
- **Key questions**: 2–3 questions each section will answer
- **Source types**: what kinds of sources you plan to use (e.g., industry reports, government data, news outlets, academic papers)

Then ask: "Does this outline look right, or would you like to adjust anything before I start researching?"

Wait for approval or adjustments. Apply any changes the user requests, then proceed.

---

## Step 4 — Research

Execute web searches targeting the approved outline. For each planned section:

- Run targeted searches to find relevant data, statistics, expert opinion, and examples
- Aim for 5–8 credible sources across the full report
- Prioritize: recent data, primary sources (original studies, official bodies, named experts), reputable outlets
- Avoid: anonymous content, undated pages, single-source claims for major statistics

Keep notes on findings per section as you go.

---

## Step 5 — Organize

Before writing, group all findings by section:

- Assign each piece of evidence to its section
- Flag any gaps (sections where data is thin) — note them briefly in the report if significant
- Flag contradictions — if sources disagree on a key fact, report both with attribution rather than picking one
- Discard anything off-scope

---

## Step 6 — Write Report

Write the report in markdown following these rules (see also `resources/report-style-guide.md`):

- **Header**: `# [Topic Title]` followed by `*Research date: [today's date]*`
- **Body sections**: use the approved outline structure, adapted to the topic — section names are flexible
- **Format**: bullet points over paragraphs; bold key numbers, percentages, and named entities
- **Closing sections** (always present, always in this order):
  - `## Key Takeaways` — 3–5 bullets distilling the single most important finding from the research
  - `## Recommended Next Steps` — 3–5 actionable bullets tailored to the stated audience
  - `## Sources` — each source as a markdown link with a descriptive title (not a raw URL), minimum 4 sources

Save the finished file to `output/` using a kebab-case filename derived from the topic (e.g., topic "AI in healthcare" → `output/ai-in-healthcare.md`).

---

## Step 7 — Deliver

After saving, send the user:

1. Confirmation that the file is saved, with the file path
2. A 2–3 bullet summary of the top findings (do not repeat the whole report)
