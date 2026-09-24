# Project: JD-to-investing job radar

This project finds, verifies and scores open job postings for one candidate, then writes them into the list format in `seeds/current_list.md`. Read this whole file before doing anything.

## The candidate (describe him accurately and never inflate)

- Seth ("Rosey") Rosenberg. Based in NYC. Accepts NYC in-person or hybrid, or US-remote. Other locations go in a separate "outside location" section, not the main tables.
- Penn Law JD 2022, magna cum laude. Dean's Prize (top 1L grades). Law Review senior editor.
- Tenth Circuit clerk (one year). Bankruptcy court term clerk, D.N.J. (three months only; treat it as exposure, not expertise).
- About 20 months at BigLaw: Quinn Emanuel (litigation and investigations) and Kirkland (litigation plus regulatory advisory).
- Morgan Stanley since Dec. 2025, Associate in CPGR, second-line credit risk. He administers credit approval authorities, applies credit policy to amendments and limit increases, supports OCC, Fed, SEC and FINRA exams, drafts credit-risk reporting and supports credit-risk review of AI-related transactions. This is not legal advice, underwriting, investing or trading.
- Admitted in NY only (2023). About 4 years post-JD. CFA Level I in progress. Limited modeling, statistics, programming or trading.
- Already in his pipeline (track them, but don't report them as discoveries): Marqeta, Harvey, Hebbia, Norm AI, General Legal.

## What he wants

He wants work organized around investigating, reading primary sources, synthesizing and writing a decision-useful conclusion. The questions should be bounded, with advisory judgment as the output. He doesn't want court time, discovery, sales or quota, spreadsheet production, generic strategy or admin. He's optimizing for high pay and unusual work.

## What the prior research found (use it to score postings)

These employers screen in two stages. Stage 1 is legal and analytic caliber, which he clears. Stage 2 is years in a named domain, usually 3 to 6+ years of restructuring, leveraged finance or payments regulation. Stage 2 is the binding constraint. The seat families that loosen it:

1. Litigation-finance underwriting (litigation is the domain; clerkships preferred).
2. Legal-AI research and build seats with base pay, not OTE.
3. Business-side regulatory risk seats at trading firms and banks (his Morgan Stanley work counts as the domain).
4. Employer-run finance academies that teach the finance (Point72 Academy, D. E. Shaw rotational, Bridgewater).
5. Embedded qualitative research at funds (Point72 Canvas, market intelligence).

Credit-intelligence legal analyst seats (Octus, 9fin, Debtwire, Fitch) are a real, well-paid niche, but they want 3 to 5+ years of restructuring practice or bankruptcy clerkships.

## Scoring rubric (score every posting you keep)

Hard excludes. These go to the "poor match" table with the reason:

- Pay is OTE, quota or variable-heavy.
- The role is pre-sales, account executive or demo-led.
- 6+ years of leveraged-finance or transactional practice is required.
- Python, statistics or systematic quant work is required.
- 5+ years of equity research, banking or buy-side experience is required.
- 10+ years of experience is required.
- The role is paralegal, document review or pure compliance operations.

Fit signals, each worth a point:

- JD required or preferred.
- "Clerkship preferred."
- Litigation experience accepted.
- "Financial services background" is a plus.
- Regulatory, legal or policy research for decisions.
- "No finance experience required," or the employer teaches the finance.
- Credit, distressed or bankruptcy subject matter.
- Fintech, crypto, AI or market-structure subject matter.
- Base pay of $150K or more.
- 2 to 5 years required (flexible floor).

Record as fields: `fit_score` (count of signals), `hard_exclude_reason` (or empty), `years_required`, `pay_min`, `pay_max`, `pay_type` (base / OTE / hourly / not listed), `jd_required` (Y/N/pref), `sales_attached` (Y/N).

## Rules

- **Verify before listing.** Every row must come from a fetch you made in this run that shows the posting is open. Snippets and aggregator titles are leads, not evidence.
- **Link to the employer posting.** Prefer the employer's own ATS URL over aggregators, and only use an aggregator link when the employer page can't be reached. Mark those rows.
- **Pay is listed pay only.** Leave it blank rather than estimate. NY, CA, CO and WA pay-transparency laws mean most postings in those states show a range, so extract it.
- **Respect sites.** Honor robots.txt and each site's terms. Send at most 1 request per second per host, with a descriptive User-Agent that includes a contact email (ask the user which one). Don't scrape LinkedIn, Indeed or Glassdoor pages. Don't log in, bypass captchas or defeat paywalls. Public ATS JSON endpoints and official APIs are fine.
- **Never apply, submit forms or contact anyone.** This project only reads.
- **Put secrets in the environment.** API keys go in `.env` (git-ignored). Never hard-code them.
