"""OpenRouter receives a fixed vocabulary and a plan shape, never the runtime inputs."""

import json
from typing import Literal

import httpx
from pydantic import Field, ValidationError

from app.assistant.config import settings
from app.assistant.errors import AppError
from app.assistant.schema.planning import StrictModel
from app.core.config import settings as app_settings

ColumnMeaning = Literal[
    "employee_id",
    "person_name",
    "department",
    "job_title",
    "date",
    "year",
    "period",
    "base_pay",
    "gross_pay",
    "net_pay",
    "allowance",
    "bonus",
    "amount",
    "hours",
    "count",
    "category",
    "other",
    "unknown",
]
SheetMeaning = Literal["employees", "payroll", "attendance", "lookup", "report", "other", "unknown"]
RepairCode = Literal["SCRIPT_ERROR", "TIME_LIMIT", "OUTPUT_LIMIT", "INVALID_OUTPUT", "WRONG_SCHEMA", "WRONG_ROWS"]


class ColumnDescription(StrictModel):
    index: int = Field(ge=1, le=40)
    meaning: ColumnMeaning
    description: str = Field(max_length=140)


class SheetDescription(StrictModel):
    meaning: SheetMeaning
    description: str = Field(max_length=240)
    columns: list[ColumnDescription] = Field(min_length=1, max_length=40)


class PublicColumn(StrictModel):
    id: str = Field(pattern=r"^c[1-9][0-9]?$")
    kind: Literal["boolean", "integer", "number", "date", "datetime", "time", "text", "mixed", "blank"]
    meaning: ColumnMeaning


class PublicSheet(StrictModel):
    id: str = Field(pattern=r"^source_[1-9][0-9]{0,2}$")
    meaning: SheetMeaning
    columns: list[PublicColumn] = Field(max_length=40)


class PublicStep(StrictModel):
    id: str = Field(pattern=r"^step_[1-9][0-9]?$")
    tool: Literal[
        "filter_rows",
        "classify_values",
        "aggregate_rows",
        "join_rows",
        "derive_column",
        "select_columns",
        "sort_rows",
        "deduplicate",
        "pivot_rows",
        "replace_values",
        "validate_rows",
    ]
    inputs: list[str] = Field(min_length=1, max_length=2)


class CodeRequest(StrictModel):
    sheets: list[PublicSheet]
    steps: list[PublicStep]
    outputs: list[str]
    repair: RepairCode | None = None
    failed_output: str | None = None

    def payload(self):
        # References come from the backend aliases, not user- or model-supplied names.
        known = {sheet.id for sheet in self.sheets}
        for step in self.steps:
            if step.id in known or not set(step.inputs) <= known:
                raise ValueError("Invalid cloud step references")
            known.add(step.id)
        if not set(self.outputs) <= known or (self.failed_output and self.failed_output not in self.outputs):
            raise ValueError("Invalid cloud output references")
        return self.model_dump()


class Script(StrictModel):
    code: str = Field(min_length=1, max_length=36_000)


INSTRUCTION = """Write Python 3 using only the standard library. Return JSON with a single code field.
Implement transform(sources, steps, outputs), returning {ref: {"columns": [str], "rows": [dict]}}
for exactly the requested outputs. Each sources[ref] has that same format. Never mutate inputs.
Process steps in the order given. Each runtime step is {id, tool, inputs, arguments}.
The public plan is the user's requested operations after normalization. Runtime arguments carry the exact
header names, private literals, and chosen operators. Read them dynamically, including the complete
column order from runtime inputs. The public catalog identifies types/semantics only, not runtime headers.
Implement only the operators used by the plan. Source cell values are strings. Preserve row order unless
the operation below says otherwise. Use Decimal(str(value)) for numeric comparisons/calculations.
Return integer for integral computed numbers, float otherwise. Do not read files, use network, print,
or use anything besides the provided inputs.

filter_rows: arguments.conditions is a list of {column, operator, value}; AND conditions. Compare str(cell).strip().
eq/ne compare with literal, contains is case-insensitive, in/not_in use the supplied list, gt/ge/lt/le use Decimal,
is_blank/not_blank use trimmed emptiness.
aggregate_rows: arguments.group_by lists columns; measures list {name, operation, column}.
Group keys are tuples of str(cell) without trimming and sorted lexicographically. Empty input with no
group keys has one group. Operations count_rows, count_distinct (unique str excluding blanks),
sum, mean, min, max. Output columns are group_by followed by measure names.
join_rows: arguments.left_on/right_on, how=left/inner, suffix. Right keys unique, match trimmed strings.
Keep left order, append right columns except right_on; add suffix to collisions. Fill unmatched with "".
derive_column: arguments.target_column, columns, operation, value, separator. Append target column.
strip/lower/upper use first str value; year parses first ISO date; concat joins all str values using
separator; coalesce picks first nonblank str; literal returns value; add/subtract/multiply/divide use two Decimal inputs.
select_columns: arguments.columns in given order, deduplicate column names. Copy projected values.
sort_rows: arguments.columns, descending, mode=auto/text/numeric. For each column auto uses numeric only if
all nonblank values parse and at least one is present. Stable lexicographic tuple of (blank, numeric or str),
blank uses an empty string and sorts last ascending.
deduplicate: arguments.columns tuple of untrimmed str values, keep first.
pivot_rows: arguments.index tuple of group columns, column is pivot header, value is measure.
Group by sorted tuples of str, append sorted unique str pivot headers after index, fill absent cells with 0.
Accumulate Decimal values in source order and normalize after each addition.
replace_values: arguments.column and mapping; look up str(cell), retaining that string when unmapped.
validate_rows: copy the dataset unchanged; the backend runs the requested checks independently.
classify_values: apply the human-approved runtime arguments.approved_by_key. Key is str(cell) for
arguments.column, or json.dumps([str(cell), ...], ensure_ascii=False) including context_columns.
Append arguments.append_columns in order. Update each row with the dictionary for its key.

On a repair request use the fixed finding to regenerate the script. WRONG_SCHEMA means different columns
or output references. WRONG_ROWS means a difference in values, order or number of rows. A script must
implement the operations. Do not change the plan or return guessed or hardcoded results.
"""


def generate(request: CodeRequest) -> str:
    key = app_settings.openrouter_api_key.get_secret_value()
    if not key:
        raise AppError(503, "Luồng Assistant cần cấu hình OPENROUTER_API_KEY.")
    body = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": INSTRUCTION},
            {"role": "user", "content": json.dumps(request.payload(), ensure_ascii=True)},
        ],
        "provider": {
            "only": ["azure"],
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
            "zdr": True,
        },
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "assistant_script",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                    "additionalProperties": False,
                },
            },
        },
        "max_completion_tokens": 6000,
    }
    try:
        with httpx.Client(timeout=settings.model_timeout, trust_env=False, follow_redirects=False) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {key}"},
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Incomplete code response")
        return Script.model_validate_json(choice["message"]["content"]).code
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, ValidationError) as error:
        raise AppError(503, "OpenRouter không trả được script hợp lệ theo cấu hình GPT và quyền riêng tư.") from error
