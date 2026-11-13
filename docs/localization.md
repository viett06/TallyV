# Source language and localized content

Use English identifiers, comments and docstrings for new source code. Current attendance VLM instructions are Vietnamese in `app/services/evidence_vlm.py`; this is an existing implementation detail, not a locale resource. Store Vietnamese presentation text in locale resources and reference it using English semantic keys.

| Resource | Purpose | Resolver |
|---|---|---|
| `app/locales/vi.json` | API messages, explanations, demo content, and localized test fixtures | `app.core.i18n.message` |
| `app/locales/attendance.vi.json` | Workbook headers, sheet names, punch labels, default rule descriptions and attendance vocabulary | `app.core.attendance` |
| `frontend/src/locales/vi.json` | UI labels, accessibility text, notifications, and document metadata | `frontend/src/i18n.ts` |

For backend messages, call `message("jobs.processing_failed", value0=error_type)`. For frontend labels, call `t("actions.next_page")`. Use placeholders for variable content and preserve the parameter names in both the resource and its call site. Frontend keys are checked by TypeScript.

Workbook labels belong to the input format. Static attendance vocabulary also supports the conservative case-text filter; it does not run a keyword classifier. Keep their existing values when reorganizing source code so existing files and evidence remain readable. Locale changes do not require an Alembic migration.

The UI continues to use Vietnamese. Source filenames and generated download filenames use English.

Attendance OCR/Gemini/JEV and historical-image UI keys have been retired. Assistant and Chatbot still have independent model/OCR presentation text; their keys remain in the shared catalogs.
