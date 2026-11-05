"""Bounded plans and typed review decisions; never executable model-generated code."""

from typing import Literal
from uuid import uuid4

from pydantic import Field

from app.assistant.schema.planning import Rewrite, StrictModel


class DataStep(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,59}$")
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
        "write_narrative",
    ]
    inputs: list[str] = Field(min_length=1, max_length=2)
    arguments: dict = Field(default_factory=dict)
    goal: str = Field(default="", max_length=1000)


class MetricBinding(StrictModel):
    dataset: str
    column: str = ""
    where: dict[str, str] = Field(default_factory=dict)
    operation: Literal["value", "sum", "count_rows"] = "value"
    row_id: str | None = None


class DataPlan(StrictModel):
    version: Literal[1] = 1
    title: str = Field(default="Data analysis", max_length=160)
    steps: list[DataStep] = Field(default_factory=list, max_length=20)
    result: str = ""
    summary: str | None = None
    bindings: dict[str, MetricBinding] = Field(default_factory=dict, max_length=100)
    tables: dict[str, str] = Field(default_factory=dict, max_length=10)
    rewrites: list[Rewrite] = Field(default_factory=list, max_length=50)
    question: str | None = None


class ClassificationDecision(StrictModel):
    step_id: str
    key: str = Field(max_length=1000)
    category: str = Field(min_length=1, max_length=160)
    save_rule: bool = False


class ResumeTask(StrictModel):
    revision: int = Field(ge=1)
    decisions: list[ClassificationDecision] = Field(default_factory=list, max_length=200)
    text: str = Field(default="", max_length=6000)
    request_key: str = Field(default_factory=lambda: str(uuid4()), min_length=8, max_length=80)


class TaskReview(StrictModel):
    revision: int = Field(ge=1)
    reviewed: bool


class RetireRule(StrictModel):
    version: int = Field(ge=1)


class ReportBindings(StrictModel):
    bindings: dict[str, MetricBinding] = Field(default_factory=dict, max_length=100)
    tables: dict[str, str] = Field(default_factory=dict, max_length=10)
    rewrites: list[Rewrite] = Field(default_factory=list, max_length=50)
    question: str | None = None


class ReportSelection(StrictModel):
    bindings: dict[str, str | None] = Field(default_factory=dict, max_length=100)
    rewrites: list[Rewrite] = Field(default_factory=list, max_length=50)
    question: None = None
