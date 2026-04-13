# LandLaw.AI MCP Server

> **By [MEOK AI Labs](https://meok.ai)** — Sovereign AI tools for everyone.

UK property law research AI. Search the Land Registry, check planning permissions, explain covenants, calculate Stamp Duty, generate Section 21/8 notices, and analyze rights of way.

[![MCPize](https://img.shields.io/badge/MCPize-Listed-blue)](https://mcpize.com/mcp/landlaw-ai)
[![MIT License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![MEOK AI Labs](https://img.shields.io/badge/MEOK_AI_Labs-255+_servers-purple)](https://meok.ai)

## Tools

| Tool | Description |
|------|-------------|
| `search_land_registry` | Search UK Land Registry by address, title number, or postcode |
| `check_planning_permission` | Check planning permission requirements for property modifications |
| `explain_covenant` | Explain restrictive or positive covenants in plain English |
| `calculate_sdlt` | Calculate Stamp Duty Land Tax for UK property purchases |
| `draft_section_notice` | Generate a Section 21 or Section 8 notice template |
| `check_right_of_way` | Analyze rights of way and easements with legal implications |

## Quick Start

```bash
pip install mcp
git clone https://github.com/CSOAI-ORG/landlaw-ai-mcp.git
cd landlaw-ai-mcp
python server.py
```

## Claude Desktop Config

```json
{
  "mcpServers": {
    "landlaw-ai": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/landlaw-ai-mcp"
    }
  }
}
```

## Pricing

| Plan | Price | Requests |
|------|-------|----------|
| Free | $0/mo | 50 requests/month |
| Pro | $19/mo | 5,000 requests/month |

[Get on MCPize](https://mcpize.com/mcp/landlaw-ai)

## Part of MEOK AI Labs

This is one of 255+ MCP servers by MEOK AI Labs. Browse all at [meok.ai](https://meok.ai) or [GitHub](https://github.com/CSOAI-ORG).

---
**MEOK AI Labs** | [meok.ai](https://meok.ai) | nicholas@meok.ai | United Kingdom
