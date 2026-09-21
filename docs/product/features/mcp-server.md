---
slug: mcp-server
title: Claude Desktop MCP Server
state: live
links:
  - kind: powered_by
    feature: canvas-hac-ingestion
  - kind: powered_by
    feature: credential-security
---

Claude can answer questions about a kid's grades and open work directly, by reading the same trusted snapshot everything else uses, without ever touching a password or driving a browser.

## Problem

Building a weekly check-in report by hand — or by having an AI drive a real Chrome session with real credentials — is slow and puts credentials somewhere they don't need to be. A parent who already uses Claude Desktop wants to just ask it, without a separate tool.

## Target users

A parent using Claude Desktop for a weekly check-in report or an ad hoc question ("what does Kate still owe in Algebra?"), who wants an answer without opening the browser app or the PDF.

## Desired outcome

`fridgesheet serve` runs an MCP server over stdio, invoked by Claude Desktop per `claude_desktop_config.json`. It exposes `list_students`, `grades`, `missing_work`, `upcoming`, `assignments`, `hac_classwork`, `status` and `refresh` as tools, all reading from (or triggering) the same snapshot [[canvas-hac-ingestion]] produces — Claude never logs in, never sees a password, and never drives a browser itself. `refresh()` is available as a tool but subject to the same cache/lock as everything else, so Claude can't accidentally hammer Canvas/HAC.

## Success metrics

- Claude Desktop's `fridgesheet:` tool list matches exactly the documented set, and results match what the CLI/web app would show for the same snapshot.
- No credential material ever appears in an MCP tool's input, output, or the server's logs.
- The server keeps working across `mcp` package major-version renames (`FastMCP` → `MCPServer`) without a hard dependency bump breaking Claude Desktop's connection.

## Non-goals

- Any tool that mutates school data, sets a flag, or writes a note — this is a read-only surface onto the same facts, not an alternate write path into [[actionable-work-model]].
- Packaging the MCP server into the Windows installer — explicitly out of scope for the Windows build (see [[windows-packaging]]).

## Notes

- "Claude never sees a password" is stated as the product's first design goal in the README, not an incidental property — logins happen inside this server's own process, and credentials are read from the OS keyring (or environment/1Password) at the moment they're used, never written anywhere the MCP transport could see them.
- `mcp` is deliberately pinned `<3` because version 2.0 renamed `FastMCP` to `MCPServer`; the server imports whichever name is available.
- Claude Desktop rewrites its own config file on exit and can silently drop unrecognized keys — a documented operational gotcha for anyone maintaining this integration, not a code concern.

## Evidence

- `fridgesheet/server.py` (`@mcp.tool()` definitions: `refresh`, `status`, `list_students`, `grades`, `assignments`, `missing_work`, `upcoming`, `hac_classwork`)
- CLI: `fridgesheet serve`
- `claude_desktop_config.example.json`
- README.md §4 ("Point Claude Desktop at it"), design goal "Claude never sees a password"
- `tests/test_server_tools.py`
