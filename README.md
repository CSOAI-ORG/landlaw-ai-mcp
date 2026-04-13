# LandLaw.AI MCP Server

**UK Property Law Research AI** | Built by [MEOK AI Labs](https://meok.ai)

MCP server for UK Land Registry searches, planning permission checks, covenant explanations, Stamp Duty calculations, Section 21/8 notices, and right of way analysis.

## Tools

| Tool | Description |
|------|-------------|
| `search_land_registry` | Search UK Land Registry by address or title number |
| `check_planning_permission` | Check PD rights and planning requirements for modifications |
| `explain_covenant` | Explain restrictive/positive covenants in plain English |
| `calculate_sdlt` | Calculate Stamp Duty Land Tax with FTB relief and surcharges |
| `draft_section_notice` | Generate Section 21 or Section 8 notice templates |
| `check_right_of_way` | Analyze rights of way and easements with legal implications |

## Quick Start

```bash
pip install mcp
python server.py
```

## Configuration (Claude Desktop)

```json
{
  "mcpServers": {
    "landlaw-ai": {
      "command": "python",
      "args": ["/path/to/landlaw-ai-mcp/server.py"]
    }
  }
}
```

## Domain Knowledge

- HM Land Registry title register structure (A/B/C sections)
- SDLT rates including FTB relief, additional property surcharge, non-resident surcharge
- GPDO 2015 permitted development rights
- Law of Property Act 1925 (covenants, easements)
- Housing Act 1988 (Section 21 and Section 8 notices)
- Town and Country Planning Act 1990
- Prescription Act 1832 (prescriptive rights)

## License

MIT - see [LICENSE](LICENSE)

---

[landlaw.ai](https://landlaw.ai) | [MEOK AI Labs](https://meok.ai)
