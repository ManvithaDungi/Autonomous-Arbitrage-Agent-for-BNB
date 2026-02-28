"""Custom exception hierarchy for the arb agent."""


class BNBAgentError(Exception):
    """Base exception for all agent errors."""


class ConfigurationError(BNBAgentError):
    """Raised when a required configuration value is missing or invalid."""


class PriceFetchError(BNBAgentError):
    """Raised when all price sources fail to return a valid price."""


class IngestionError(BNBAgentError):
    """Raised when a data source cannot be fetched."""


class ExecutionError(BNBAgentError):
    """Raised when a trade execution fails at the MCP layer."""


class MCPError(BNBAgentError):
    """Raised on MCP server connection or protocol errors."""
