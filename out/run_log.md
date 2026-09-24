# Run log 2026-09-24

User-Agent: `JobRadar/0.1 (personal job-search tool; read-only; contact: sethnrosenberg@gmail.com)`

## Channels

| Channel | Queried | Candidates | Verified open | Kept | Notes |
|---|---:|---:|---:|---:|---|
| phase1:seed-verify | 33 | 33 | 20 | — | 2 seed rows closed, 4 unverifiable |

## Blocked or skipped

- `ag.ny.gov`: http-403: server refused this client (HTTP 403: The page could not be loaded properly.); not worked around
- `www.citadel.com`: challenge: bot wall (HTTP 403); not bypassed
- `www.citadelsecurities.com`: challenge: bot wall on robots.txt (HTTP 403)
- `www.jobleads.com`: challenge: bot wall (HTTP 403); not bypassed
- `www.kerrisdalecap.com`: robots: robots.txt unreachable: gave up after 4 attempts (ConnectTimeout: [WinError 10060] A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond)

## Failures

- `GET https://www.selbyjennings.com/jobs` (phase1:seed-closed): gave up after 4 attempts (HTTP 429)
- `GET https://www.kerrisdalecap.com/robots.txt` (phase1:seed-closed): gave up after 4 attempts (ConnectTimeout: [WinError 10060] A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond)

## Requests by host

58 requests logged (4 live, 54 cache hits or blocks).

| Host | Requests |
|---|---:|
| ms.wd5.myworkdayjobs.com | 15 |
| boards-api.greenhouse.io | 10 |
| ag.ny.gov | 5 |
| api.ashbyhq.com | 4 |
| careers.point72.com | 3 |
| careers.burfordcapital.com | 2 |
| capstonedc.wd501.myworkdayjobs.com | 2 |
| www.citadelsecurities.com | 2 |
| citi.wd5.myworkdayjobs.com | 2 |
| www.kerrisdalecap.com | 2 |
| www.janestreet.com | 1 |
| www.deshaw.com | 1 |
| guggenheiminvestment.wd5.myworkdayjobs.com | 1 |
| careers.fitch.group | 1 |
| www.jobleads.com | 1 |
| www.citadel.com | 1 |
| www.horizonengage.com | 1 |
| www.politicalriskjobs.com | 1 |
| work.mercor.com | 1 |
| api.lever.co | 1 |
| www.selbyjennings.com | 1 |

<details><summary>Every endpoint hit this run</summary>

| Time | Channel | Method | URL | Status | Cache |
|---|---|---|---|---|---|
| 17:49:56 | phase1:seed-open | GET | https://careers.burfordcapital.com/job/New-York-Vice-President,-Commercial-Underwriting-NY-10017/1331385600/ | 200 | hit |
| 17:49:56 | phase1:seed-open | GET | https://www.janestreet.com/jobs/main.json | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/janestreet/jobs/8031535002?pay_transparency=true | 404 | hit |
| 17:49:57 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/bridgewater89/jobs/8294673002?pay_transparency=true | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://www.deshaw.com/careers/rotational-associates-program-6020 | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://api.ashbyhq.com/posting-api/job-board/harvey?includeCompensation=true | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://careers.point72.com/CSJobDetail?jobName=point72-academy-2026-investment-analyst-program-for-experienced-professionals-us&jobCode=CPA-0014729 | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://careers.point72.com/CSJobDetail?jobName=fundamental-researcher-canvas&jobCode=PMI-0005694 | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://guggenheiminvestment.wd5.myworkdayjobs.com/wday/cxs/guggenheiminvestment/External/job/330-Madison-Ave-2nd-Fl-New-York-City-NYUS/Attorney---Restructuring_JR-2026-101206 | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/capstonedc/jobs/5775608004?pay_transparency=true | 404 | hit |
| 17:49:57 | phase1:seed-open | POST | https://capstonedc.wd501.myworkdayjobs.com/wday/cxs/capstonedc/Capstone/jobs | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://capstonedc.wd501.myworkdayjobs.com/wday/cxs/capstonedc/Capstone/job/Washington-DC/Associate--Financial-Services-Investment---Policy_JR100031 | 200 | hit |
| 17:49:57 | phase1:seed-open | GET | https://ag.ny.gov/robots.txt | 403 |  |
| 17:49:58 | phase1:seed-open | GET | https://ag.ny.gov/job-postings/attorneys | 403 |  |
| 17:49:59 | phase1:seed-open | GET | https://ag.ny.gov/job-postings/other | 403 |  |
| 17:50:00 | phase1:seed-open | GET | https://ag.ny.gov/job-postings/fellowships | 403 |  |
| 17:50:01 | phase1:seed-open | GET | https://ag.ny.gov/job-postings/investigators | 403 |  |
| 17:50:01 | phase1:seed-open | GET | https://api.ashbyhq.com/posting-api/job-board/rain?includeCompensation=true | 200 | hit |
| 17:50:01 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/octus/jobs/5147468007?pay_transparency=true | 200 | hit |
| 17:50:01 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/octus/jobs/5134117007?pay_transparency=true | 200 | hit |
| 17:50:02 | phase1:seed-open | GET | https://careers.fitch.group/job/New-York-Director,-Covenant-Analyst-NY-10001/1423937633/ | 200 | hit |
| 17:50:02 | phase1:seed-open | GET | https://careers.burfordcapital.com/job/Chicago-Vice-President%2C-Patent-Underwriting-IL-60654/1331845700/ | 200 | hit |
| 17:50:02 | phase1:seed-open | GET | https://www.jobleads.com/us/job/merger-arbitrage-event-driven-analyst--new-york--e87cb41c7c749b8ca8ba4ca838af28eda | 403 |  |
| 17:50:02 | phase1:seed-open | GET | https://www.citadel.com/careers/details/equities-investment-associate-ashler-capital-global-equities-surveyor-capital/ | 403 |  |
| 17:50:02 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/towerresearchcapital/jobs?content=true | 200 | hit |
| 17:50:02 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/towerresearchcapital/jobs/8113102?pay_transparency=true | 200 | hit |
| 17:50:03 | phase1:seed-open | GET | https://www.citadelsecurities.com/robots.txt | 403 |  |
| 17:50:03 | phase1:seed-open | GET | https://www.citadelsecurities.com/careers/details/quantitative-researcher-quantitative-research-analyst/ | challenge |  |
| 17:50:03 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/alphasense/jobs/8817957002?pay_transparency=true | 200 | hit |
| 17:50:03 | phase1:seed-open | GET | https://boards-api.greenhouse.io/v1/boards/alphasense/jobs/8476088002?pay_transparency=true | 200 | hit |
| 17:50:03 | phase1:seed-open | GET | https://www.horizonengage.com/careers | 200 | hit |
| 17:50:03 | phase1:seed-open | GET | https://www.politicalriskjobs.com/jobs/616539882-director-global-macro | 200 | hit |
| 17:50:03 | phase1:seed-open | GET | https://api.ashbyhq.com/posting-api/job-board/harvey?includeCompensation=true | 200 | hit |
| 17:50:03 | phase1:seed-open | GET | https://api.ashbyhq.com/posting-api/job-board/legora?includeCompensation=true | 200 | hit |
| 17:50:03 | phase1:seed-open | GET | https://work.mercor.com/jobs/list_AAABmKp5u6OLRyAhur1NUaEr/legal-expert | 200 | hit |
| 17:50:03 | phase1:seed-closed | GET | https://careers.point72.com/CSSitemap | 200 | hit |
| 17:50:03 | phase1:seed-closed | GET | https://boards-api.greenhouse.io/v1/boards/octus/jobs?content=true | 200 | hit |
| 17:50:03 | phase1:seed-closed | GET | https://api.lever.co/v0/postings/ion?mode=json | 200 | hit |
| 17:50:04 | phase1:seed-closed | POST | https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs | 200 | hit |
| 17:50:04 | phase1:seed-closed | GET | https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/job/New-York-New-York-United-States/Risk-Arbitrage-Trader--Director_26986544-1 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://www.selbyjennings.com/jobs | 429 |  |
| 17:50:18 | phase1:seed-closed | POST | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/jobs | 200 | hit |
| 17:50:18 | phase1:seed-closed | POST | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/jobs | 200 | hit |
| 17:50:18 | phase1:seed-closed | POST | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/jobs | 200 | hit |
| 17:50:18 | phase1:seed-closed | POST | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/jobs | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/New-York-New-York-United-States-of-America/Equity-Research---Analyst-Associate--Hardlines--Broadlines---Food-Retail--New-York-_JR043569-1 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/Hong-Kong-Hong-Kong/Equity-Research--Greater-China-Technology-Hardware--Analyst-Associate_JR042741 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/Taipei-Taiwan/Equity-research--Greater-China-Semiconductor--Analyst-Associate_JR042024 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/New-York-New-York-United-States-of-America/Equity-Research-Associate---Fintech---Payments_JR037294 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/New-York-New-York-United-States-of-America/Equity-Research-Associate---Softlines-Apparel-Footwear_JR042444-1 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/1585-Broadway--NY/Equity-Research-Associate---Asset-Managers--Brokers-and-Exchanges_JR041556-1 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/New-York-New-York-United-States-of-America/Equity-Research-Associate---Autos---Shared-Mobility_JR040528-2 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/Hong-Kong-Hong-Kong/Equity-Research--HK-China-Transportation---Associate--VP_JR041466 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/Hong-Kong-Hong-Kong/Equity-Research--China-Industrials--Associate--VP_JR041388 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/Hong-Kong-Hong-Kong/Equity-research--China-Healthcare--Analyst-Associate_JR040714 | 200 | hit |
| 17:50:18 | phase1:seed-closed | GET | https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/job/Hong-Kong-Hong-Kong/Equity-Research--China-Strategist--Associate--VP_JR040707 | 200 | hit |
| 17:51:56 | phase1:seed-closed | GET | https://www.kerrisdalecap.com/robots.txt | error |  |
| 17:51:56 | phase1:seed-closed | GET | https://www.kerrisdalecap.com/analyst-hiring/ | robots |  |

</details>
