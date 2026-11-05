"""Microsoft Agent Framework execution graph behind the durable SQL step scheduler."""

import asyncio

from agent_framework import WorkflowBuilder, WorkflowContext, executor

from app.assistant.errors import AppError, InputError
from app.assistant.services import tools
from app.core.i18n import message


def execute_tool(step, inputs, context):
    """SQL receipts checkpoint between tool graphs; no framework pickle is persisted."""
    failure = []

    @executor(id="validate_tool")
    async def validate(payload: dict, ctx: WorkflowContext[dict, dict]):
        tools.validate_arguments(step)
        await ctx.send_message(payload)

    @executor(id="execute_tool")
    async def execute(payload: dict, ctx: WorkflowContext[dict, dict]):
        try:
            result = tools.execute(step, inputs, context)
        except Exception as error:
            failure.append(error)
            await ctx.send_message({"tool_failed": True})
            return
        await ctx.send_message(result)

    @executor(id="verify_output")
    async def verify(result: dict, ctx: WorkflowContext[dict, dict]):
        if failure:
            await ctx.yield_output({"tool_failed": True})
            return
        if not isinstance(result.get("rows"), list) or not isinstance(result.get("columns"), list):
            raise InputError(message("assistant.data.invalid_tool_output"))
        if len(result["columns"]) != len(set(result["columns"])):
            raise InputError(message("assistant.data.invalid_tool_output"))
        if any(not row.get("id") or not isinstance(row.get("lineage"), list) for row in result["rows"]):
            raise InputError(message("assistant.data.invalid_tool_output"))
        await ctx.yield_output(result)

    async def run():
        builder = WorkflowBuilder(
            name="tallyv-data-tool-v1", start_executor=validate, output_from=[verify], max_iterations=6
        )
        builder.add_edge(validate, execute).add_edge(execute, verify)
        result = None
        async for event in builder.build().run({"step_id": step.id}, stream=True):
            if event.type == "output":
                result = event.data
        if failure:
            raise failure[0]
        if result is None:
            raise AppError(503, message("assistant.data.workflow_failed"))
        return result

    try:
        return asyncio.run(run())
    except Exception:
        if failure:
            raise failure[0]
        raise
