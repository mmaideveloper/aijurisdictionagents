"""Run `python examples/typed_tool_loop_demo.py`; synthetic, offline, no secrets."""
import asyncio

from aijurisdictionagents.llm.tool_loop import ModelStep, RegisteredTool, run_tool_loop
from aijurisdictionagents.llm.turn_contracts import AgentTurnContext, ToolCall, ToolDefinition


async def main() -> None:
    async def infer(history, definitions, remaining):
        if not history:
            return ModelStep(calls=(ToolCall(call_id="demo-1", tool_id="getVersion", arguments_json="{}"),))
        return ModelStep("Synthetic system version: demo. Legal outputs require human review.")

    async def execute(arguments):
        return {"version": "demo"}

    tool = RegisteredTool(ToolDefinition(
        tool_id="getVersion", description="Synthetic public system version",
        input_schema_json='{"type":"object","properties":{},"additionalProperties":false}',
        required_scope="internal_public_legal_read", approval_required=False,
    ), execute, lambda: True, lambda payload: payload)
    result = await run_tool_loop(AgentTurnContext(), infer, [tool])
    assert result.reason == "completed" and result.calls == 1
    print(f"{result.reason}: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
