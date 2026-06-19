"""Prove CLIO's tool gateway invokes clio-author (via the MCP bridge). No LM."""

from clio_agent.tools.mcp_config import spec_from_declaration
from clio_agent.tools.gateway import build_gateway
from clio_agent.tools.execution import create_sync_tool_executor

LAUNCH = "/home/shazzadul/Illinois_Tech/Summer26/RA/clio-author/scripts/mcp_bridge_launch.sh"
spec = spec_from_declaration("clioauthor", {"command": LAUNCH, "args": []}, source="demo")
print("spec ok:", spec.name, spec.transport, "errors:", spec.validation_errors)

gateway = build_gateway({"clioauthor": spec})
ex = create_sync_tool_executor(gateway)
try:
    names = ex.get_tool_names()
    mine = [n for n in names if "clioauthor" in n]
    print("CLIO discovered clio-author tools:", mine)
    res = ex.call_tool(
        "clioauthor_run",
        {
            "action": "meta_review",
            "payload": {
                "reviews": [
                    {"Overall": 8, "Decision": "Accept"},
                    {"Overall": 3, "Decision": "Reject"},
                    {"Overall": 6, "Decision": "Accept"},
                ]
            },
        },
    )
    print("CLIO -> clio-author meta_review RESULT:", str(res)[:400])
finally:
    ex.close()
