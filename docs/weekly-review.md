# Payroll review calendar

The named payroll month starts on the previous month's 26th and ends on its own 25th, inclusively. Dates on or after the 26th belong to the next named period.

| Payroll period | Attendance window | Saturday request dates |
|---|---|---|
| October 2026 | September 26 – October 25 | September 26; October 3, 10, 17, 24 |
| November 2026 | October 26 – November 25 | October 31; November 7, 14, 21 |
| January 2027 | December 26 – January 25 | December 26; January 2, 9, 16, 23 |

Each Saturday opens a review cycle. Its summary date is the following Monday. The Saturday's payroll period owns the cycle, including when Monday is in the next payroll period. The October 24 request and October 26 summary therefore belong to October payroll. November payroll provides a link back to that closing cycle.

The module `app/services/review_calendar.py` owns date-to-period attribution, inclusive bounds and actual weekday calculations. It uses `Asia/Ho_Chi_Minh` for today's date. `/api/bootstrap` returns the current payroll period, its exact date window, cycles and carryover links. On October 30, 2026, the current payroll period is November 2026. The UI follows the current period until the user selects another one; the current-period button restores that behavior. Date states describe planned dates rather than proof of an outgoing email or a department reply.

## Intake and provenance

New weekly subjects declare the payroll period and Saturday request date:

```text
[DCC] [2026-11] [WEEK:2026-10-31] Synthetic department summary
```

The weekly tag must identify a Saturday between the declared period's 26th and 25th. Invalid, ambiguous or mismatched tags require manual review. Receipt timestamps never determine the cycle, so late replies retain their declared cycle.

Workbook attendance dates must also fall within the declared payroll period. September 26 and October 25 are valid for October payroll; September 25 and October 26 are rejected for that period. An out-of-period row is reported as an error rather than silently imported under the wrong payroll month.

Historical monthly emails without weekly tags remain under the unassigned-cycle filter. Migration `a6c832f03190` introduced nullable cycle fields. Migration `b703d8a21c45` updates stored period bounds to the payroll cutoff without changing case identifiers, source records, HR decisions or unassigned cycles. Existing local attendance dates were checked against the new bounds before migration.

A case retains the cycle of its original intake. A later correction or duplicate email does not move it into another cycle. Weekly cycles identify collection rounds; attendance-date validation uses the full owning payroll window.

## Shared scope

Dashboard, inbox, cases and Excel export accept `period` and `cycle` query parameters. Omit `cycle` for the whole payroll period, use a Saturday's ISO date for one cycle, or use `unassigned` for historical monthly intake. Excel includes request and summary dates after the existing columns.

Synthetic email jobs carry the selected payroll period and cycle into the worker. Sample attendance dates stay within that payroll window; case codes and message IDs include the cycle. Tests capture SMTP in memory rather than adding messages to the existing mailbox.

## Verification

```bash
python -m pytest -q
ruff check app main.py scripts tests
alembic check
cd frontend && npm run build
```

Tests cover the 25th/26th cutoff, cross-year ownership, leap February, actual weekday counts, Vietnam midnight, late replies, unassigned history, carryover links, period filtering/export, payroll date validation, and synthetic intake in another year.
