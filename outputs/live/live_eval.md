# Live evaluation against the blinded manual review

Run 2026-10-28 21:41. Reference: the manual review of 100 reports (coded blind, before seeing any AI label). Rules v1.2 for the live runs.

## Agreement with the manual review (exact agreement, Cohen's kappa)

| Field | Earlier AI run, rules v1.1 | Earlier AI run, rules v1.2 | Local: granite4.2:8b |
|---|---|---|---|
| Primary failure mode | 93% (0.90) | 92% (0.89) | 76% (0.67) |
| Secondary failure mode | 86% (0.61) | 93% (0.83) | 70% (0.29) |
| Phase of use | 93% (0.88) | 96% (0.93) | 82% (0.69) |
| Severity | 61% (0.44) | 85% (0.78) | 39% (0.14) |
| Likely contributor | 86% (0.62) | 88% (0.75) | 23% (0.00) |
| Retained fragment | 99% (0.93) | 100% (1.00) | 95% (0.64) |
| User harm | 100% (1.00) | 100% (1.00) | 100% (1.00) |
| Severity within one level | 98% | 99% | 98% |
| All seven fields identical | 43% | 63% | 4% |
| Reports scored | 100 | 100 | 100 |

## Safety check: would the serious cases still reach a person?

Reports whose manual coding triggers human review (severity S3 or worse, a retained fragment or harm to the user), and how many of them each model's labels would also send to review (its own S3+, fragment, user-harm or low-confidence flags).

| | Earlier AI run, rules v1.1 | Earlier AI run, rules v1.2 | Local: granite4.2:8b |
|---|---|---|---|
| Serious cases caught | 13 of 40 (32%) | 34 of 40 (85%) | 12 of 40 (30%) |
| Reports sent to review in total | 14 | 34 | 17 |

## Cost, speed and the agent loop

| Model | Reports coded | Retries | Rejected | Errors | Sent to review | API calls | Cost (USD) | Cost per report | Seconds per call |
|---|---|---|---|---|---|---|---|---|---|
| Local: granite4.2:8b | 100 | 0 | 0 | 0 | 17 | 100 | 0 (local) | 0 | 9.75 |

Token totals: granite4.2:8b: 403,840 input, 0 read from cache, 0 written to cache, 13,680 output

## Where the new runs disagree with the manual review (severity and failure mode)

- **Local: granite4.2:8b, primary failure mode** (24): manual vs AI. 0001625425-2025-01096 (FM01 vs FM02), 17912320 (FM01 vs FM02), 3006260740-2023-00342 (FM09 vs FM13), 3006260740-2023-01306 (FM05 vs FM04), 3006260740-2023-02877 (FM12 vs FM03), 3006260740-2023-02890 (FM01 vs FM02), 3006260740-2023-06018 (FM05 vs FM04), 3006260740-2023-06058 (FM06 vs FM01), 3006260740-2023-06089 (FM03 vs FM04), 3006260740-2024-01485 (FM05 vs FM02), 3006260740-2024-01545 (FM08 vs FM02), 3006260740-2024-03410 (FM01 vs FM02), 3006260740-2024-03429 (FM12 vs FM01), 3006260740-2024-03619 (FM12 vs FM01), 3006260740-2024-05734 (FM05 vs FM04) ...
- **Local: granite4.2:8b, severity** (61): manual vs AI. 0001625425-2023-01114 (S3 vs S2), 0001625425-2023-01220 (S3 vs S2), 0001625425-2024-00979 (S3 vs S2), 1317056-2024-00005 (S3 vs S2), 1317056-2025-00002 (S3 vs S2), 17912320 (S3 vs S2), 2245270-2023-00001 (S3 vs S2), 2245270-2024-00086 (S3 vs S2), 3006260740-2023-00342 (S3 vs S2), 3006260740-2023-00588 (S1 vs S2), 3006260740-2023-00655 (S3 vs S2), 3006260740-2023-01192 (S3 vs S2), 3006260740-2023-01200 (S3 vs S2), 3006260740-2023-01306 (S1 vs S2), 3006260740-2023-02778 (S2 vs S3) ...

## How to read this

- The manual review is one reviewer's coding, not ground truth; disagreements need reading, not just counting.
- The earlier runs coded reports inside a chat session; the new runs use fixed settings (temperature 0 for local models), so they are the repeatable result.
- Local token counts are prompt tokens Ollama actually processed; text it reused from the previous call is not counted again.
- Kappa corrects for agreement expected by chance: above 0.80 almost perfect, 0.61-0.80 substantial, 0.41-0.60 moderate.
