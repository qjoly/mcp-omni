"""MCP server for Omni Talos cluster management."""

import asyncio
import json
import os
import subprocess
import tempfile
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_omni.omni_client import OmniClient, SERVICE_ACCOUNT_STATUS_TYPE

OMNI_ENDPOINT = os.environ.get("OMNI_ENDPOINT", "")
OMNI_SERVICE_ACCOUNT_KEY = os.environ.get("OMNI_SERVICE_ACCOUNT_KEY", "")

app = Server("mcp-omni")
_client: OmniClient | None = None


def _get_client() -> OmniClient:
    global _client
    if _client is None:
        if not OMNI_ENDPOINT or not OMNI_SERVICE_ACCOUNT_KEY:
            raise RuntimeError("OMNI_ENDPOINT and OMNI_SERVICE_ACCOUNT_KEY must be set")
        _client = OmniClient(OMNI_ENDPOINT, OMNI_SERVICE_ACCOUNT_KEY)
    return _client


def _omnictl(*args: str, input_data: str | None = None) -> str:
    """Run omnictl for operations not yet in the native gRPC client."""
    env = os.environ.copy()
    result = subprocess.run(
        ["omnictl"] + list(args),
        capture_output=True, text=True, env=env,
        input=input_data, timeout=60,
    )
    if result.returncode != 0:
        err = result.stderr or result.stdout
        return f"Error (exit {result.returncode}):\n{err}"
    return result.stdout or "(no output)"


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="omni_list_clusters",
            description="List all Talos clusters managed by Omni.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="omni_get_cluster",
            description="Get details for a specific cluster including Talos and Kubernetes versions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string", "description": "Cluster name"},
                },
                "required": ["cluster_name"],
            },
        ),
        Tool(
            name="omni_cluster_status",
            description="Get the status of a cluster (ready machines, phase, conditions).",
            inputSchema={
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string", "description": "Cluster name"},
                },
                "required": ["cluster_name"],
            },
        ),
        Tool(
            name="omni_list_machines",
            description="List all machines available in Omni.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="omni_list_cluster_machines",
            description="List all machines assigned to clusters.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="omni_get_resource",
            description=(
                "Get one or all resources of a given fully-qualified type. "
                "Type must be the full name, e.g. 'Clusters.omni.sidero.dev', "
                "'MachineStatuses.omni.sidero.dev', 'MachineSets.omni.sidero.dev'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {"type": "string", "description": "Fully-qualified resource type"},
                    "resource_id": {"type": "string", "description": "Optional resource ID (omit to list all)"},
                    "namespace": {"type": "string", "description": "Namespace (default: 'default')"},
                },
                "required": ["resource_type"],
            },
        ),
        Tool(
            name="omni_get_kubeconfig",
            description="Download the admin kubeconfig for a cluster.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string", "description": "Cluster name"},
                },
                "required": ["cluster_name"],
            },
        ),
        Tool(
            name="omni_get_talosconfig",
            description="Download the talosconfig for a cluster.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string", "description": "Cluster name"},
                },
                "required": ["cluster_name"],
            },
        ),
        Tool(
            name="omni_machine_logs",
            description="Get logs for a specific machine.",
            inputSchema={
                "type": "object",
                "properties": {
                    "machine_id": {"type": "string", "description": "Machine ID"},
                    "tail": {"type": "integer", "description": "Number of lines (default: 100)"},
                    "log_format": {
                        "type": "string",
                        "enum": ["raw", "omni", "dmesg"],
                        "description": "Log format (default: raw)",
                    },
                },
                "required": ["machine_id"],
            },
        ),
        Tool(
            name="omni_delete_resource",
            description="Delete a resource by fully-qualified type and ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {"type": "string", "description": "Fully-qualified resource type"},
                    "resource_id": {"type": "string", "description": "Resource ID"},
                    "namespace": {"type": "string", "description": "Namespace (default: 'default')"},
                },
                "required": ["resource_type", "resource_id"],
            },
        ),
        Tool(
            name="omni_apply",
            description="Create or update Omni resources from YAML content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "yaml_content": {"type": "string", "description": "YAML resource definition"},
                },
                "required": ["yaml_content"],
            },
        ),
        Tool(
            name="omni_cluster_template_sync",
            description="Apply a cluster template YAML to create or update a cluster.",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_yaml": {"type": "string", "description": "Cluster template YAML"},
                    "dry_run": {"type": "boolean", "description": "Show diff only (default: false)"},
                },
                "required": ["template_yaml"],
            },
        ),
        Tool(
            name="omni_cluster_template_export",
            description="Export an existing cluster as a template YAML.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string", "description": "Cluster name"},
                },
                "required": ["cluster_name"],
            },
        ),
        Tool(
            name="omni_serviceaccount_list",
            description="List all service accounts.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="omni_serviceaccount_create",
            description="Create a new service account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Service account name"},
                    "ttl": {"type": "string", "description": "Key TTL (e.g. '8760h' for 1 year)"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="omni_cluster_kubernetes_upgrade",
            description="Upgrade Kubernetes version for a cluster.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string", "description": "Cluster name"},
                    "version": {"type": "string", "description": "Target Kubernetes version (e.g. '1.30.0')"},
                },
                "required": ["cluster_name", "version"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    result_text = await asyncio.get_event_loop().run_in_executor(
        None, _dispatch_sync, name, arguments
    )
    return [TextContent(type="text", text=result_text)]


def _fmt(items: list[dict] | dict) -> str:
    return json.dumps(items, indent=2)


def _dispatch_sync(name: str, args: dict[str, Any]) -> str:
    try:
        client = _get_client()
    except Exception as e:
        return f"Client init error: {e}"

    try:
        if name == "omni_list_clusters":
            items = client.list_clusters()
            if not items:
                return "(no clusters)"
            rows = ["CLUSTER                        TALOS            KUBERNETES"]
            for it in items:
                m = it.get("metadata", {})
                s = it.get("spec", {})
                rows.append(
                    f"{m.get('id','?'):<30} {s.get('talos_version','?'):<16} {s.get('kubernetes_version','?')}"
                )
            return "\n".join(rows)

        elif name == "omni_get_cluster":
            item = client.get_cluster(args["cluster_name"])
            return _fmt(item)

        elif name == "omni_cluster_status":
            item = client.get_cluster_status(args["cluster_name"])
            return _fmt(item)

        elif name == "omni_list_machines":
            items = client.list_machines()
            if not items:
                return "(no machines)"
            rows = ["MACHINE                                          CONNECTED  ADDRESS"]
            for it in items:
                m = it.get("metadata", {})
                s = it.get("spec", {})
                rows.append(
                    f"{m.get('id','?'):<48} {str(s.get('connected', '?')):<10} {s.get('management_address','?')}"
                )
            return "\n".join(rows)

        elif name == "omni_list_cluster_machines":
            items = client.list_cluster_machines()
            return _fmt(items)

        elif name == "omni_get_resource":
            rt = args["resource_type"]
            ns = args.get("namespace", "default")
            rid = args.get("resource_id")
            if rid:
                return _fmt(client.get_resource(rt, rid, ns))
            else:
                return _fmt(client.list_resources(rt, ns))

        elif name == "omni_get_kubeconfig":
            data = client.get_kubeconfig(args["cluster_name"])
            return data.decode() if isinstance(data, bytes) else str(data)

        elif name == "omni_get_talosconfig":
            data = client.get_talosconfig(args["cluster_name"])
            return data.decode() if isinstance(data, bytes) else str(data)

        elif name == "omni_machine_logs":
            return client.get_machine_logs(
                args["machine_id"],
                tail_lines=args.get("tail", 100),
            )

        elif name == "omni_delete_resource":
            client.delete_resource(
                args["resource_type"],
                args["resource_id"],
                args.get("namespace", "default"),
            )
            return f"Deleted {args['resource_type']}/{args['resource_id']}"

        # ── omnictl-backed tools ──────────────────────────────────

        elif name == "omni_apply":
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(args["yaml_content"])
                tmp = f.name
            try:
                return _omnictl("apply", "-f", tmp)
            finally:
                os.unlink(tmp)

        elif name == "omni_cluster_template_sync":
            with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
                f.write(args["template_yaml"])
                tmp = f.name
            try:
                if args.get("dry_run"):
                    return _omnictl("cluster", "template", "diff", "-f", tmp)
                return _omnictl("cluster", "template", "sync", "-f", tmp)
            finally:
                os.unlink(tmp)

        elif name == "omni_cluster_template_export":
            return _omnictl("cluster", "template", "export", "--cluster", args["cluster_name"])

        elif name == "omni_serviceaccount_list":
            items = client.list_resources(SERVICE_ACCOUNT_STATUS_TYPE)
            return _fmt(items) if items else _omnictl("serviceaccount", "list")

        elif name == "omni_serviceaccount_create":
            cmd = ["serviceaccount", "create", args["name"]]
            if args.get("ttl"):
                cmd += ["--ttl", args["ttl"]]
            return _omnictl(*cmd)

        elif name == "omni_cluster_kubernetes_upgrade":
            return _omnictl(
                "cluster", "kubernetes", "upgrade",
                args["cluster_name"], "--to", args["version"],
            )

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        return f"Error: {e}"


def main() -> None:
    asyncio.run(_run_server())


async def _run_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
