# Migration Guide

**Upgrading to Helix-Agent-Orchestration v1.0.1**

**Version**: 1.0.0  
**Last Updated**: April 2, 2026

---

## Overview

This guide helps you migrate from previous versions of helix-agent-orchestration to version 1.0.1, which includes comprehensive improvements in testing, documentation, error handling, and performance optimization.

### What's New in v1.0.1

- **32+ Comprehensive Tests**: Full test coverage for all core functionality
- **Advanced Documentation**: API reference, performance guide, troubleshooting
- **Enhanced Error Handling**: 30+ custom exception classes
- **Performance Benchmarks**: Detailed performance analysis and optimization tips
- **Integration Tests**: Real-world integration scenarios with agent cores
- **100% Backward Compatible**: All existing code continues to work

---

## Migration Steps

### Step 1: Update Package

```bash
# Update to latest version
pip install --upgrade helix-agent-orchestration

# Or install from GitHub
pip install git+https://github.com/Deathcharge/helix-agent-orchestration.git@main
```

### Step 2: Review Breaking Changes

**Good news**: There are **NO breaking changes** in v1.0.1. All existing code will continue to work without modifications.

### Step 3: Update Error Handling (Optional)

While not required, we recommend updating your error handling to use the new custom exception classes for better error management:

#### Before (v1.0.0)

```python
try:
    result = await orchestrator.coordinate()
except Exception as e:
    print(f"Error: {e}")
```

#### After (v1.0.1)

```python
from helix_orchestration.exceptions import (
    CoordinationError,
    AgentNotFoundError,
    TaskExecutionError,
)

try:
    result = await orchestrator.coordinate()
except CoordinationError as e:
    logger.error(f"Coordination failed: {e.message}")
    logger.error(f"Recovery action: {get_error_recovery_action(e)}")
except AgentNotFoundError as e:
    logger.error(f"Agent {e.agent_id} not found")
except TaskExecutionError as e:
    logger.error(f"Task {e.task_id} failed on agent {e.agent_id}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

### Step 4: Update Configuration (Optional)

The configuration format remains the same, but you can now use additional options:

```python
config = {
    "max_agents": 18,
    "coordination_timeout": 30,
    "handshake_timeout": 5,
    # New optional settings
    "enable_metrics_caching": True,
    "metrics_cache_ttl": 60,
    "enable_compression": False,
}

orchestrator = AgentOrchestrator(**config)
```

### Step 5: Run Tests

Verify your code works with the new version:

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run your tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/helix_orchestration
```

---

## Import Path Updates

### Core Imports

All core imports remain the same:

```python
# These imports continue to work
from helix_orchestration.agents.agent_orchestrator import AgentOrchestrator
from helix_orchestration.coordination.coordination_hub import CoordinationHub
from helix_orchestration.agents.agent_registry import AgentRegistry
```

### New Exception Imports

New exception classes are available in a dedicated module:

```python
# New: Import custom exceptions
from helix_orchestration.exceptions import (
    OrchestratorError,
    AgentRegistrationError,
    CoordinationError,
    TaskExecutionError,
    EthicsValidationError,
    ConfigurationError,
    # ... and 24+ more
)
```

---

## API Changes

### No Breaking Changes

All existing APIs remain unchanged. New methods and parameters are additive only.

### New Methods

#### Exception Utilities

```python
from helix_orchestration.exceptions import (
    format_error,
    get_error_recovery_action,
    ErrorRecoveryStrategy,
)

# Format error for logging
formatted = format_error(error)

# Get recovery action
action = get_error_recovery_action(error)

# Check if error should be retried
should_retry = ErrorRecoveryStrategy.should_retry(error)
```

### New Features

#### Metrics Caching

```python
# Enable metrics caching for better performance
config = {
    "enable_metrics_caching": True,
    "metrics_cache_ttl": 60,  # Cache for 60 seconds
}

orchestrator = AgentOrchestrator(**config)
```

#### Compression

```python
# Enable compression for stored metrics
config = {
    "enable_compression": True,
    "compression_level": 6,
}

orchestrator = AgentOrchestrator(**config)
```

---

## Configuration Migration

### v1.0.0 Configuration

```python
config = {
    "max_agents": 18,
    "coordination_timeout": 30,
    "handshake_timeout": 5,
}
```

### v1.0.1 Configuration (Recommended)

```python
config = {
    # Core settings (unchanged)
    "max_agents": 18,
    "coordination_timeout": 30,
    "handshake_timeout": 5,
    
    # New optional settings
    "enable_ethics": True,
    "enable_resonance": True,
    "enable_autonomy_scoring": True,
    "enable_metrics_caching": True,
    "metrics_cache_ttl": 60,
    "enable_compression": False,
    "log_level": "DEBUG",
    "consensus_threshold": 0.8,
}
```

---

## Testing Migration

### Running Tests

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest tests/

# Run specific test category
pytest tests/ -m unit
pytest tests/ -m integration
pytest tests/ -m slow

# Run with coverage
pytest tests/ --cov=src/helix_orchestration --cov-report=html
```

### Writing New Tests

Use the new test fixtures and mocks:

```python
import pytest
from tests.conftest import MockAgent, MockCoordinationHub

@pytest.mark.asyncio
async def test_my_feature():
    # Create mock agent
    agent = MockAgent("test-agent", "TestAgent")
    await agent.initialize()
    
    # Test your feature
    result = await agent.execute_task({"id": "task-1", "type": "test"})
    
    assert result["status"] == "success"
```

---

## Performance Optimization

### Before (v1.0.0)

```python
# Basic usage without optimization
orchestrator = AgentOrchestrator()
await orchestrator.initialize()

# Each query hits the database
metrics1 = await orchestrator.get_metrics()
metrics2 = await orchestrator.get_metrics()  # Redundant query
```

### After (v1.0.1)

```python
# Optimized usage with caching
config = {
    "enable_metrics_caching": True,
    "metrics_cache_ttl": 60,
}

orchestrator = AgentOrchestrator(**config)
await orchestrator.initialize()

# First query hits database
metrics1 = await orchestrator.get_metrics()

# Second query uses cache
metrics2 = await orchestrator.get_metrics()  # Uses cache
```

---

## Documentation Updates

### New Documentation

- **[API Reference](API_REFERENCE.md)**: Complete API documentation
- **[Performance Guide](PERFORMANCE.md)**: Performance tuning and optimization
- **[Troubleshooting Guide](TROUBLESHOOTING.md)**: Common issues and solutions
- **[Architecture Guide](ARCHITECTURE.md)**: System architecture and design

### Updated Examples

- **[Basic Orchestration](../examples/basic_orchestration.py)**: Updated with best practices
- **[Error Handling](../examples/basic_orchestration.py#L300)**: New error handling patterns
- **[Performance Monitoring](../examples/basic_orchestration.py#L400)**: Monitoring examples

---

## Troubleshooting

### Issue: Import Errors

**Problem**: `ModuleNotFoundError: No module named 'helix_orchestration'`

**Solution**:
```bash
# Reinstall package
pip install --force-reinstall helix-agent-orchestration

# Or install from source
pip install git+https://github.com/Deathcharge/helix-agent-orchestration.git@main
```

### Issue: Version Mismatch

**Problem**: `ImportError: cannot import name 'CoordinationError'`

**Solution**:
```bash
# Update to latest version
pip install --upgrade helix-agent-orchestration

# Verify version
python -c "import helix_orchestration; print(helix_orchestration.__version__)"
```

### Issue: Test Failures

**Problem**: Tests fail after upgrade

**Solution**:
```bash
# Reinstall test dependencies
pip install -r requirements-test.txt

# Run tests with verbose output
pytest tests/ -v

# Check for compatibility issues
pytest tests/ --tb=short
```

---

## Rollback Instructions

If you need to rollback to v1.0.0:

```bash
# Uninstall current version
pip uninstall helix-agent-orchestration

# Install previous version
pip install helix-agent-orchestration==1.0.0
```

---

## Support

### Getting Help

- **Documentation**: See [docs/](../) for comprehensive guides
- **Issues**: Report bugs on [GitHub Issues](https://github.com/Deathcharge/helix-agent-orchestration/issues)
- **Discussions**: Join [GitHub Discussions](https://github.com/Deathcharge/helix-agent-orchestration/discussions)

### Reporting Issues

When reporting issues, include:
1. Version: `python -c "import helix_orchestration; print(helix_orchestration.__version__)"`
2. Python version: `python --version`
3. Error message and traceback
4. Minimal reproducible example

---

## FAQ

### Q: Is v1.0.1 backward compatible?

**A**: Yes, 100% backward compatible. All existing code continues to work without changes.

### Q: Do I need to update my code?

**A**: No, but we recommend updating error handling to use the new exception classes for better error management.

### Q: What if I find a bug?

**A**: Report it on [GitHub Issues](https://github.com/Deathcharge/helix-agent-orchestration/issues) with a minimal reproducible example.

### Q: How do I upgrade?

**A**: Run `pip install --upgrade helix-agent-orchestration`

### Q: Can I use v1.0.1 with my v1.0.0 code?

**A**: Yes, without any modifications. All APIs are backward compatible.

---

## Checklist

Use this checklist to ensure a smooth migration:

- [ ] Update package: `pip install --upgrade helix-agent-orchestration`
- [ ] Review breaking changes (none in v1.0.1)
- [ ] Update error handling (optional but recommended)
- [ ] Update configuration (optional)
- [ ] Run tests: `pytest tests/`
- [ ] Review new documentation
- [ ] Update your code to use new features (optional)
- [ ] Test in development environment
- [ ] Deploy to production

---

## Next Steps

After upgrading to v1.0.1:

1. **Review Documentation**: Check out the new [API Reference](API_REFERENCE.md)
2. **Optimize Performance**: Follow the [Performance Guide](PERFORMANCE.md)
3. **Handle Errors Better**: Use the new [exception classes](../src/helix_orchestration/exceptions.py)
4. **Run Tests**: Execute the comprehensive [test suite](../tests/)
5. **Monitor Performance**: Use the [performance benchmarks](../benchmarks/)

---

**Last Updated**: April 2, 2026  
**Status**: Production Ready
