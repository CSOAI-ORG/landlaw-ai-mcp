<div align="center">

# Landlaw Ai MCP

**LandLaw.AI MCP Server - UK Property Law Research**

[![PyPI](https://img.shields.io/pypi/v/meok-landlaw-ai-mcp)](https://pypi.org/project/meok-landlaw-ai-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MEOK AI Labs](https://img.shields.io/badge/MEOK_AI_Labs-MCP_Server-purple)](https://meok.ai)

</div>

## Overview

LandLaw.AI MCP Server - UK Property Law Research
Built by MEOK AI Labs | https://landlaw.ai

UK Land Registry searches, planning permission checks, covenant explanations,
Stamp Duty calculations, Section 21/8 notices, and right of way analysis.

## Tools

| Tool | Description |
|------|-------------|
| `search_land_registry` | Search UK Land Registry by address, title number, or postcode. |
| `check_planning_permission` | Check planning permission requirements for a property modification. |
| `explain_covenant` | Explain a restrictive or positive covenant in plain English. |
| `calculate_sdlt` | Calculate Stamp Duty Land Tax for a UK property purchase. |
| `draft_section_notice` | Generate a Section 21 or Section 8 notice template. |
| `check_right_of_way` | Analyze a right of way or easement and explain its implications. |

## Installation

```bash
pip install meok-landlaw-ai-mcp
```

## Usage with Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "landlaw-ai": {
      "command": "python",
      "args": ["-m", "meok_landlaw_ai_mcp.server"]
    }
  }
}
```

## Usage with FastMCP

```python
from mcp.server.fastmcp import FastMCP

# This server exposes 6 tool(s) via MCP
# See server.py for full implementation
```

## License

MIT © [MEOK AI Labs](https://meok.ai)
