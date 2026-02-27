# start_mcp.ps1 — Starts the BNBChain MCP server for the arb agent to connect to
# Run this BEFORE starting orchestrator.py

$env:PRIVATE_KEY = (Get-Content .env | Select-String "^PRIVATE_KEY=").Line.Split("=",2)[1].Trim()
$env:PORT = "3001"

Write-Host "🚀 Starting BNBChain MCP server on http://localhost:3001 ..." -ForegroundColor Cyan
Write-Host "   Private key loaded from .env" -ForegroundColor Gray
Write-Host "   Press Ctrl+C to stop`n" -ForegroundColor Gray

npx -y @bnb-chain/mcp@latest --sse
