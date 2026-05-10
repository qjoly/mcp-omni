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

### Via Smithery (recommended)

[![smithery badge](https://smithery.ai/badge/@qjoly/mcp-omni)](https://smithery.ai/server/@qjoly/mcp-omni)

Install directly from [Smithery](https://smithery.ai/server/@qjoly/mcp-omni) — it handles configuration and registration in your MCP client automatically.

### Pre-built binary (macOS / Linux)

```bash
brew tap qjoly/tap
brew install qjoly/tap/mcp-omni
```

Or download the latest binary from the [Releases](../../releases) page.

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
