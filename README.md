# mcp-omni

MCP server for [Omni](https://github.com/siderolabs/omni) Talos cluster management.

Connects Claude Desktop (or any MCP client) directly to the Omni gRPC API using native PGP signing — no `omnictl` subprocess required.

## Features

- List and inspect clusters, machines, machine sets
- Get cluster status, kubeconfig, talosconfig
- Delete resources
- Apply YAML / sync cluster templates
- Manage service accounts
- Trigger Kubernetes upgrades

## Installation

### Pre-built binary

Download the latest binary for your platform from the [Releases](../../releases) page.

### From source

```bash
git clone https://github.com/qjoly/mcp-omni
cd mcp-omni
pip install -e .
```

## Configuration

Add to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "omni": {
      "command": "/path/to/mcp-omni",
      "env": {
        "OMNI_ENDPOINT": "https://your-omni.example.com",
        "OMNI_SERVICE_ACCOUNT_KEY": "<base64-service-account-key>"
      }
    }
  }
}
```

Generate a service account key with:

```bash
omnictl serviceaccount create my-mcp-account --role Admin --ttl 8760h
```

## Authentication

The server uses Omni service account keys (base64-encoded JSON with PGP signing) and communicates directly over gRPC — no `omnictl` binary needed at runtime.
