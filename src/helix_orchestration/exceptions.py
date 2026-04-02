"""
Custom exceptions for helix-agent-orchestration.

This module defines a hierarchy of custom exceptions for better error
handling and reporting across the orchestration system.
"""


class OrchestratorError(Exception):
    """Base exception for all orchestrator-related errors."""

    def __init__(self, message: str, error_code: str = "UNKNOWN"):
        self.message = message
        self.error_code = error_code
        super().__init__(f"[{error_code}] {message}")


class OrchestratorInitializationError(OrchestratorError):
    """Raised when orchestrator initialization fails."""

    def __init__(self, message: str):
        super().__init__(message, "INIT_ERROR")


class OrchestratorShutdownError(OrchestratorError):
    """Raised when orchestrator shutdown fails."""

    def __init__(self, message: str):
        super().__init__(message, "SHUTDOWN_ERROR")


class AgentRegistrationError(OrchestratorError):
    """Raised when agent registration fails."""

    def __init__(self, message: str, agent_id: str = None):
        self.agent_id = agent_id
        super().__init__(message, "REGISTRATION_ERROR")


class AgentNotFoundError(OrchestratorError):
    """Raised when a requested agent is not found."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        message = f"Agent '{agent_id}' not found"
        super().__init__(message, "AGENT_NOT_FOUND")


class AgentUnregistrationError(OrchestratorError):
    """Raised when agent unregistration fails."""

    def __init__(self, message: str, agent_id: str = None):
        self.agent_id = agent_id
        super().__init__(message, "UNREGISTRATION_ERROR")


class CoordinationError(OrchestratorError):
    """Raised when multi-agent coordination fails."""

    def __init__(self, message: str, agents_involved: int = None):
        self.agents_involved = agents_involved
        super().__init__(message, "COORDINATION_ERROR")


class CoordinationTimeoutError(CoordinationError):
    """Raised when coordination times out."""

    def __init__(self, timeout_seconds: float, agents_involved: int = None):
        message = f"Coordination timed out after {timeout_seconds} seconds"
        super().__init__(message, agents_involved)
        self.timeout_seconds = timeout_seconds


class HandshakeError(OrchestratorError):
    """Raised when handshake protocol fails."""

    def __init__(self, message: str, phase: str = None):
        self.phase = phase
        super().__init__(message, "HANDSHAKE_ERROR")


class HandshakePhaseError(HandshakeError):
    """Raised when a specific handshake phase fails."""

    def __init__(self, phase: str, message: str):
        full_message = f"Handshake phase '{phase}' failed: {message}"
        super().__init__(full_message, phase)


class TaskExecutionError(OrchestratorError):
    """Raised when task execution fails."""

    def __init__(self, message: str, task_id: str = None, agent_id: str = None):
        self.task_id = task_id
        self.agent_id = agent_id
        super().__init__(message, "TASK_EXECUTION_ERROR")


class TaskTimeoutError(TaskExecutionError):
    """Raised when task execution times out."""

    def __init__(self, task_id: str, timeout_seconds: float, agent_id: str = None):
        message = f"Task '{task_id}' timed out after {timeout_seconds} seconds"
        super().__init__(message, task_id, agent_id)
        self.timeout_seconds = timeout_seconds


class MetricsError(OrchestratorError):
    """Raised when metrics collection or retrieval fails."""

    def __init__(self, message: str, metric_name: str = None):
        self.metric_name = metric_name
        super().__init__(message, "METRICS_ERROR")


class UCFMetricsError(MetricsError):
    """Raised when UCF metrics collection fails."""

    def __init__(self, message: str):
        super().__init__(message, "UCF")


class EthicsValidationError(OrchestratorError):
    """Raised when ethics validation fails."""

    def __init__(self, message: str, violation_type: str = None):
        self.violation_type = violation_type
        super().__init__(message, "ETHICS_VIOLATION")


class ResonanceEngineError(OrchestratorError):
    """Raised when resonance engine encounters an error."""

    def __init__(self, message: str):
        super().__init__(message, "RESONANCE_ERROR")


class AutonomyScoringError(OrchestratorError):
    """Raised when autonomy scoring fails."""

    def __init__(self, message: str, agent_id: str = None):
        self.agent_id = agent_id
        super().__init__(message, "AUTONOMY_SCORING_ERROR")


class ConfigurationError(OrchestratorError):
    """Raised when configuration is invalid."""

    def __init__(self, message: str, config_key: str = None):
        self.config_key = config_key
        super().__init__(message, "CONFIG_ERROR")


class InvalidConfigurationError(ConfigurationError):
    """Raised when a configuration value is invalid."""

    def __init__(self, config_key: str, invalid_value, expected_type: str = None):
        message = f"Invalid configuration for '{config_key}': {invalid_value}"
        if expected_type:
            message += f" (expected {expected_type})"
        super().__init__(message, config_key)
        self.invalid_value = invalid_value
        self.expected_type = expected_type


class MissingConfigurationError(ConfigurationError):
    """Raised when a required configuration is missing."""

    def __init__(self, config_key: str):
        message = f"Missing required configuration: '{config_key}'"
        super().__init__(message, config_key)


class StateManagementError(OrchestratorError):
    """Raised when state management fails."""

    def __init__(self, message: str):
        super().__init__(message, "STATE_ERROR")


class StateLoadError(StateManagementError):
    """Raised when state loading fails."""

    def __init__(self, message: str, state_file: str = None):
        self.state_file = state_file
        super().__init__(f"Failed to load state: {message}")


class StateSaveError(StateManagementError):
    """Raised when state saving fails."""

    def __init__(self, message: str, state_file: str = None):
        self.state_file = state_file
        super().__init__(f"Failed to save state: {message}")


class CommunicationError(OrchestratorError):
    """Raised when inter-agent communication fails."""

    def __init__(self, message: str, sender_id: str = None, receiver_id: str = None):
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        super().__init__(message, "COMMUNICATION_ERROR")


class MCPToolError(OrchestratorError):
    """Raised when MCP tool integration fails."""

    def __init__(self, message: str, tool_name: str = None):
        self.tool_name = tool_name
        super().__init__(message, "MCP_TOOL_ERROR")


class ResourceExhaustedError(OrchestratorError):
    """Raised when system resources are exhausted."""

    def __init__(self, message: str, resource_type: str = None):
        self.resource_type = resource_type
        super().__init__(message, "RESOURCE_EXHAUSTED")


class MaxAgentsExceededError(ResourceExhaustedError):
    """Raised when maximum agent limit is exceeded."""

    def __init__(self, max_agents: int, current_agents: int):
        message = f"Maximum agents ({max_agents}) exceeded. Current: {current_agents}"
        super().__init__(message, "AGENTS")
        self.max_agents = max_agents
        self.current_agents = current_agents


class MemoryExhaustedError(ResourceExhaustedError):
    """Raised when memory limit is exceeded."""

    def __init__(self, message: str, memory_used_mb: float = None):
        self.memory_used_mb = memory_used_mb
        super().__init__(message, "MEMORY")


class TimeoutError(OrchestratorError):
    """Raised when an operation times out."""

    def __init__(self, message: str, timeout_seconds: float = None):
        self.timeout_seconds = timeout_seconds
        super().__init__(message, "TIMEOUT")


class OperationNotSupportedError(OrchestratorError):
    """Raised when an operation is not supported."""

    def __init__(self, operation: str, reason: str = None):
        message = f"Operation '{operation}' is not supported"
        if reason:
            message += f": {reason}"
        super().__init__(message, "NOT_SUPPORTED")


class InternalError(OrchestratorError):
    """Raised when an internal error occurs."""

    def __init__(self, message: str, error_details: dict = None):
        self.error_details = error_details or {}
        super().__init__(message, "INTERNAL_ERROR")


# ============================================================================
# Error Recovery Helpers
# ============================================================================

class ErrorRecoveryStrategy:
    """Base class for error recovery strategies."""

    @staticmethod
    def should_retry(error: OrchestratorError) -> bool:
        """Determine if an error should trigger a retry."""
        retryable_errors = (
            CoordinationTimeoutError,
            TaskTimeoutError,
            CommunicationError,
            TemporaryError,
        )
        return isinstance(error, retryable_errors)

    @staticmethod
    def get_retry_delay(error: OrchestratorError, attempt: int) -> float:
        """Get retry delay in seconds (exponential backoff)."""
        base_delay = 0.1
        max_delay = 30.0
        delay = min(base_delay * (2 ** attempt), max_delay)
        return delay


class TemporaryError(OrchestratorError):
    """Raised for temporary errors that might be retried."""

    def __init__(self, message: str):
        super().__init__(message, "TEMPORARY_ERROR")


# ============================================================================
# Exception Utilities
# ============================================================================

def format_error(error: OrchestratorError) -> str:
    """Format an error for logging or display."""
    lines = [
        f"Error Code: {error.error_code}",
        f"Message: {error.message}",
    ]
    
    # Add context-specific information
    if hasattr(error, "agent_id") and error.agent_id:
        lines.append(f"Agent ID: {error.agent_id}")
    
    if hasattr(error, "task_id") and error.task_id:
        lines.append(f"Task ID: {error.task_id}")
    
    if hasattr(error, "timeout_seconds") and error.timeout_seconds:
        lines.append(f"Timeout: {error.timeout_seconds}s")
    
    return "\n".join(lines)


def get_error_recovery_action(error: OrchestratorError) -> str:
    """Get recommended recovery action for an error."""
    recovery_actions = {
        "INIT_ERROR": "Check configuration and dependencies",
        "SHUTDOWN_ERROR": "Force shutdown and cleanup resources",
        "REGISTRATION_ERROR": "Verify agent configuration",
        "AGENT_NOT_FOUND": "Check agent ID and registration status",
        "COORDINATION_ERROR": "Retry coordination or reduce agent count",
        "TASK_EXECUTION_ERROR": "Retry task or check agent status",
        "ETHICS_VIOLATION": "Review ethics constraints",
        "CONFIG_ERROR": "Fix configuration and restart",
        "TIMEOUT": "Increase timeout or reduce workload",
        "RESOURCE_EXHAUSTED": "Free resources or scale down",
    }
    
    return recovery_actions.get(error.error_code, "Check logs for details")
