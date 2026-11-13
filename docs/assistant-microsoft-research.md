# Microsoft AI assistant architecture: evidence for TallyV

> Status as of 2026-11-14: dated architecture research, not a deployment guide. Upstream sources were not revalidated in the documentation sync. Current Assistant modes and implemented limits are documented in [assistant.md](assistant.md); attendance image processing uses a separate [PII/VLM background pipeline](vlm-evidence.md).

Research date: 2026-11-04. Scope: publicly documented AI agent architecture, not Microsoft 365, Outlook, Office licensing, or an implementation change. The recommendations below are TallyV design decisions informed by Microsoft sources. They do not describe proprietary Copilot internals, establish a universal Microsoft architecture, or confer Microsoft or hospital compliance certification.

## 1. Start with one agent and explicit workflow control

Microsoft's architecture guidance recommends the lowest complexity that reliably meets requirements. A direct model call suits one-step tasks; a single agent with tools is often the enterprise default. Multiagent orchestration adds coordination cost, latency, and failure modes and should address an observed need. Tool loops need iteration limits. [Azure Architecture Center: orchestration patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

Agent Framework supports tool-using agents, explicit graph/function workflows, sessions, context providers, middleware, and MCP clients. Its overview distinguishes open-ended agents from workflows with controlled execution paths and recommends ordinary functions for tasks they can solve. Supported providers include Ollama; Microsoft patterns do not require Azure inference. [Agent Framework overview](https://learn.microsoft.com/en-us/agent-framework/overview/)

**TallyV implication:** one conversational planner can propose a typed task plan. A workflow executes authorized functions for file inspection, transformation, classification, aggregation, validation, and report rendering. These are separate responsibilities, not necessarily separate AI agents. Introduce specialist agents only when evaluations show a single agent cannot reliably handle the domain/tool scope.

## 2. Separate context, conversation state, and durable business knowledge

Context providers enrich inputs before agent execution and can process information afterward. Agent Framework supports conversational history and file-backed memory. Stable scopes can share memory across sessions; applications must authorize externally supplied scopes. Session-specific state belongs to the session, not a shared provider instance. [Context providers](https://learn.microsoft.com/en-us/agent-framework/concepts/agents/conversations/context-providers)

**TallyV implication:**

- Context contains relevant instructions, column metadata, role labels, approved classification rules, and tool-result summaries.
- Run state contains file versions, selected sheets, the plan, step status, output references, and unresolved questions.
- Business memory contains HR-confirmed rules and template mappings, versioned and scoped to the authorized organization/user.
- Raw workbooks and full derived tables stay in authorized artifact storage. Retrieval supplies necessary evidence; summarization must not silently omit rows from computation.

A model suggestion is not automatically an approved business rule. Corrections should preserve the rule author, scope, effective version, and approval decision.

## 3. Human input and resumable execution

Agent Framework workflows use typed external request/response handling to wait for human input and route a response back to the requesting executor. [Human-in-the-loop](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop)

Checkpoints preserve executor state, pending messages and requests, and shared state. Python provides in-memory, file, and Cosmos checkpoint storage options; in-memory storage does not survive process restarts. Durable cross-process use needs persistent storage. [Checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)

**TallyV implication:** persist a task when classification or template mapping is ambiguous, let HR return later, and resume the matching task/version. Existing PostgreSQL/job storage can remain the application system of record. A PostgreSQL checkpoint implementation would require an evaluated adapter; it is not asserted here to be a documented built-in provider. Checkpointing alone does not guarantee exactly-once writes. Application-owned idempotency keys, immutable input versions, and recorded tool receipts are needed for safe retries. Changes to classification invalidate dependent statistics and report drafts.

## 4. Tools, policy, and approval are application responsibilities

Function middleware can inspect tool inputs, transform results, and control execution. Other middleware intercepts agent runs or model requests. [Middleware](https://learn.microsoft.com/en-us/agent-framework/agents/middleware/)

Agent Framework provides function-tool approval requests that applications must surface and resolve across subsequent agent runs. [Tool approval](https://learn.microsoft.com/en-us/agent-framework/agents/tools/tool-approval)

Microsoft's shared-responsibility guidance identifies orchestration, tool behavior, identity scope, and data handling as agent security concerns, including prompt injection that drives actions and excessive agency. A managed platform does not eliminate application responsibilities. [AI agent shared responsibility](https://learn.microsoft.com/en-us/azure/security/fundamentals/shared-responsibility-ai-agent)

**TallyV implication:** authorize every invocation against the authenticated caller, artifact ownership, allowed operation, and current approval version. Validate typed inputs and outputs outside the model. Treat workbook cells and document text as untrusted data. Read/transform/draft tools can execute within a permitted task; publishing, overwriting an external source, sending mail, or SAP writes require a separately authorized action. MCP can standardize a tool connection but does not replace these controls.

## 5. Code execution needs a separate isolation design

Microsoft distinguishes user identity isolation from hosted session isolation. A hosted session contains sandbox compute and persisted files; it is not the conversation history. Its documented Foundry design uses a VM-isolated sandbox, with explicit identity/session mappings. The related AgentServer/Framework hosting packages are identified as prerelease in the source. [Foundry hosted agent isolation](https://devblogs.microsoft.com/agent-framework/foundry-hosted-agent-isolation-with-microsoft-agent-framework/)

**TallyV implication:** prefer bounded data tools first. For cases requiring generated Python, use a disposable execution environment with per-task files, resource limits, controlled packages, and restricted network/secrets. A normal worker subprocess or a framework installation is not itself a verified sandbox. Hosted Foundry is one optional platform, not an MVP prerequisite; sandbox choice needs a separate feasibility and security test.

## 6. Observe and evaluate the complete task

Agent Framework emits OpenTelemetry traces, logs, and metrics and requires configured exporters. Sensitive message/tool-content capture is optional; metadata tracing does not require collecting raw HR inputs. [Observability](https://learn.microsoft.com/en-us/agent-framework/agents/observability)

Microsoft's AI Well-Architected guidance distinguishes model evaluation from whole-system testing. It recommends business-aligned metrics and human-validated input/output datasets. Agentic testing should check the complete input-to-output flow, correct tool calls and parameters, failure handling, security, and performance; deterministic logic also needs conventional tests. [Test and evaluate AI workloads](https://learn.microsoft.com/en-us/azure/well-architected/ai/test)

**TallyV implication:** record a trace for each run/step/tool call using IDs and timings, with controlled retention. Evaluate intent resolution, classification accuracy and abstention, exact row counts, source traceability, template placement, restart/retry recovery, and cross-user isolation. Use synthetic HR workbooks and known expected reports initially. Do not treat a second model agreeing with the first as proof that arithmetic or source mapping is correct.

## Decision summary

Use Microsoft's documented agent/workflow separation as an architectural reference. Retain deterministic calculations and report-value insertion behind narrow tool interfaces; put natural-language interpretation and uncertain semantic classification in model-assisted steps. Design explicit review, versioning, durable state, runtime authorization, and evaluation before expanding autonomy. Choose one orchestration framework after a small comparative proof; combining LangGraph and Agent Framework to orchestrate the same task would introduce overlapping state and retry ownership without a demonstrated need.
