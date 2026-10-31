# Source language and localized content

Write identifiers, comments, docstrings, developer messages, and model instructions in English. Store Vietnamese presentation text in locale resources and reference it using English semantic keys.

| Resource | Purpose | Resolver |
|---|---|---|
| `app/locales/vi.json` | API messages, explanations, demo content, and localized test fixtures | `app.core.i18n.message` |
| `app/locales/attendance.vi.json` | Workbook headers, sheet names, punch labels, and classification vocabulary | `app.core.attendance` |
| `frontend/src/locales/vi.json` | UI labels, accessibility text, notifications, and document metadata | `frontend/src/i18n.ts` |

For backend messages, call `message("jobs.processing_failed", value0=error_type)`. For frontend labels, call `t("actions.next_page")`. Use placeholders for variable content and preserve the parameter names in both the resource and its call site. Frontend keys are checked by TypeScript.

Workbook labels and classification vocabulary belong to the input format. Keep their existing values when reorganizing source code so existing files and evidence remain readable. Locale changes do not require an Alembic migration.

The UI continues to use Vietnamese. Source filenames and generated download filenames use English.
