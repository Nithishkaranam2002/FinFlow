# FinFlow MCP server (read only)

`mcp/finflow_mcp/` is a small [Model Context Protocol](https://modelcontextprotocol.io) server
that lets Claude Desktop answer questions about FinFlow invoices. It runs on your Mac over
stdio, logs in to the FinFlow API with the account you configure, and reuses that session.

It is built on the official MCP Python SDK (`mcp` 2.x). In SDK 2.x the high-level server
formerly called FastMCP is named `MCPServer` (`from mcp.server.mcpserver import MCPServer`).

## Read only by design

There are **no write tools**. Claude can look things up, but approving, rejecting,
correcting or paying an invoice always stays with a person in the FinFlow app, where the
approval policy, role checks and audit trail apply. Every tool is marked `readOnlyHint`.

## Tools

| Tool | What it returns |
|------|-----------------|
| `list_pending_approvals()` | Invoices waiting for approval: number, vendor, total, who must approve (Approver or Controller), plain-English attention reasons |
| `get_invoice(invoice_number)` | One invoice: status, amounts, dates, fraud flags, attention reasons, line items, approval history |
| `invoices_needing_attention(limit=25)` | Everything in Review Required plus open invoices with fraud signals, fraud first, each with reasons |
| `spend_by_vendor(days=30)` | Spend per vendor from approved (and paid) invoices in the last N days, highest first |

The attention reasons use the same wording as the "Why this needs attention" box on the
invoice page. The only API change was an optional `invoice_number` filter on
`GET /api/v1/invoices/` (authenticated and tenant scoped, like the rest of that endpoint).

## Setup on this Mac

1. FinFlow must be running (`make fresh` or `make up`) so `http://localhost:8000` answers.
2. `uv` is installed at `/opt/homebrew/bin/uv`. Claude Desktop does not use your shell
   `PATH`, so the config uses the full path. The first launch creates
   `mcp/finflow_mcp/.venv`, which takes a few seconds.
3. Open the Claude Desktop config file (create it if it does not exist):

   ```
   ~/Library/Application Support/Claude/claude_desktop_config.json
   ```

   From Claude Desktop you can also get there with **Settings → Developer → Edit Config**.

4. Add the `finflow` entry under `mcpServers` (merge it if the file already has other servers).
   Replace the password placeholder with the AP clerk password from the
   "Test credentials" table in the README:

   ```json
   {
     "mcpServers": {
       "finflow": {
         "command": "/opt/homebrew/bin/uv",
         "args": [
           "--directory",
           "/Users/nithishkaranam/Downloads/projects/projects /FinFlow/mcp/finflow_mcp",
           "run",
           "finflow-mcp"
         ],
         "env": {
           "FINFLOW_API_URL": "http://localhost:8000",
           "FINFLOW_EMAIL": "clerk@acmecorp.com",
           "FINFLOW_PASSWORD": "<AP clerk password from the README>"
         }
       }
     }
   }
   ```

   The AP clerk account is enough because every tool only reads. On another machine, change
   the `--directory` path (keep the space in `projects /FinFlow`, JSON handles it) and the `uv` path
   (`which uv`).

5. **Fully quit Claude Desktop (Cmd+Q, not just closing the window) and open it again.**
   The `finflow` server and its four tools then appear under the tools (hammer/plug) menu.

## Sample questions

1. "Which invoices are waiting for approval, and who needs to approve each one?"
2. "Show me invoice HTLP-2026-04471. Who approved it and when?"
3. "Which invoices need attention right now and why? Start with anything that looks like fraud."
4. "What did we spend per vendor in the last 30 days? Give me the top 5."

## Troubleshooting

- Server log: `~/Library/Logs/Claude/mcp-server-finflow.log`
- "Cannot reach the FinFlow API": start the stack, then check `curl http://localhost:8000/health`.
- "FinFlow rejected FINFLOW_EMAIL / FINFLOW_PASSWORD": fix the `env` values, then quit and reopen
  Claude Desktop. After `make fresh` the seeded test users are recreated with the same passwords.
- Run the server by hand to check it starts (it waits silently for MCP messages; Ctrl+C to stop):

  ```bash
  cd mcp/finflow_mcp && FINFLOW_EMAIL=clerk@acmecorp.com FINFLOW_PASSWORD='...' uv run finflow-mcp
  ```
