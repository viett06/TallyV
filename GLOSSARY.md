# TallyV

Business language for HR data work and report review. Definitions describe business concepts independently of their implementation.

## Assistant work

**Task**:
An HR request to transform or review specified data and produce an agreed result.
_Avoid_: Chat, job, report

**Business Contract**:
The agreed objective, source scope, population, rules, counting units, expected outputs and acceptance criteria for a Task.
_Avoid_: Prompt, assumptions

**Source Snapshot**:
An immutable version of an input file and its declared business scope used for a particular result.
_Avoid_: Latest file, working copy

**Run**:
A processing effort against one fixed version of a Task's Business Contract and Source Snapshots.
_Avoid_: Task, execution attempt

**Execution Attempt**:
One attempt to carry out part of a Run, including an unsuccessful attempt followed by a technical correction.
_Avoid_: Revision, new request

**Result Revision**:
An immutable version of a Task's result bundle associated with its sources, Business Contract and review history.
_Avoid_: Execution attempt, edited original

**Result Bundle**:
The related datasets, reports, explanations and traceability evidence presented together for HR review.
_Avoid_: Report, single file

**Lineage**:
The relationship between a result, its contributing source records and the transformations applied to them.
_Avoid_: Explanation, source filename

**Business Decision**:
An explicit HR choice that resolves an ambiguity affecting the meaning of a result, such as a classification rule or counting unit.
_Avoid_: Model confidence, inferred approval

**Verification Finding**:
An observed failure, uncertainty or advisory condition produced by an identified check against a result.
_Avoid_: Model opinion, general error

**HR Approval**:
An authorized person's acceptance of one specific Result Revision under its stated verification scope.
_Avoid_: Successful execution, generated report, publication

**Approved Procedure**:
A versioned method accepted for repeated use within a stated business scope and input structure.
_Avoid_: Memorized answer, universal rule
