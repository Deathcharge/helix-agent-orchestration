# Troubleshooting Guide

**Version**: 1.0.0  
**Last Updated**: April 2, 2026

---

## Table of Contents

1. [Common Issues](#common-issues)
2. [Error Messages](#error-messages)
3. [Debugging Techniques](#debugging-techniques)
4. [Performance Issues](#performance-issues)
5. [Integration Issues](#integration-issues)
6. [FAQ](#faq)

---

## Common Issues

### Issue 1: Orchestrator Initialization Fails

**Symptoms**
- `OrchestratorInitializationError` raised
- Orchestrator cannot start
- Application crashes on startup

**Possible Causes**
1. Invalid configuration parameters
2. Missing dependencies
3. Resource constraints (memory, file descriptors)
4. Port conflicts

**Solutions**

```python
# Check configuration
config = {
    "max_agents": 18,
    "coordination_timeout": 30,
    "handshake_timeout": 5,
}

# Verify all required fields are present
required_fields = ["max_agents", "coordination_timeout"]
for field in required_fields:
    if field not in config:
        raise ValueError(f"Missing required field: {field}")

# Try with default configuration
from helix_orchestration.agents.agent_orchestrator import AgentOrchestrator

try:
    orchestrator = AgentOrchestrator()
    await orchestrator.initialize()
except Exception as e:
    print(f"Error: {e}")
    # Check logs for details
```

**Debugging Steps**
1. Check system resources: `free -h`, `df -h`
2. Verify dependencies: `pip list | grep helix`
3. Check logs: `tail -f orchestration.log`
4. Test with minimal configuration

---

### Issue 2: Agent Registration Fails

**Symptoms**
- `AgentRegistrationError` raised
- Agents cannot be registered
- Agent count stuck at 0

**Possible Causes**
1. Agent already registered
2. Maximum agent count exceeded
3. Invalid agent configuration
4. Agent initialization failed

**Solutions**

```python
from helix_orchestration.exceptions import (
    AgentRegistrationError,
    MaxAgentsExceededError,
)

try:
    await orchestrator.register_agent(agent)
except MaxAgentsExceededError as e:
    print(f"Max agents exceeded: {e.max_agents}")
    # Either increase max_agents or unregister unused agents
    
except AgentRegistrationError as e:
    print(f"Registration failed: {e.message}")
    # Check agent configuration
    print(f"Agent ID: {e.agent_id}")
```

**Debugging Steps**
1. Verify agent is initialized: `agent.status == "initialized"`
2. Check agent ID is unique
3. Verify max_agents setting
4. Check agent configuration

---

### Issue 3: Coordination Timeout

**Symptoms**
- Coordination takes longer than expected
- `CoordinationTimeoutError` raised
- System becomes unresponsive

**Possible Causes**
1. Too many agents
2. Slow network
3. High system load
4. Timeout value too low

**Solutions**

```python
# Increase timeout
orchestrator = AgentOrchestrator(
    coordination_timeout=60,  # Increase from default 30
    handshake_timeout=10,     # Increase from default 5
)

# Or reduce agent count
if len(orchestrator.agents) > 10:
    # Consider using multiple orchestrators
    pass

# Monitor coordination time
import time
start = time.time()
result = await orchestrator.coordinate()
elapsed = time.time() - start
print(f"Coordination took {elapsed:.2f}s")
```

**Debugging Steps**
1. Check system load: `top`, `htop`
2. Monitor network: `iftop`, `nethogs`
3. Check agent count
4. Increase timeout gradually
5. Profile coordination code

---

### Issue 4: Task Execution Fails

**Symptoms**
- Tasks don't complete
- `TaskExecutionError` raised
- Results are empty or None

**Possible Causes**
1. Agent not initialized
2. Invalid task format
3. Agent crashed or shutdown
4. Resource exhaustion

**Solutions**

```python
from helix_orchestration.exceptions import TaskExecutionError

try:
    # Verify agent is ready
    if agent.status != "initialized":
        await agent.initialize()
    
    # Verify task format
    task = {
        "id": "task-001",
        "type": "analysis",
        "data": {...}
    }
    
    result = await orchestrator.execute_task(task)
    
except TaskExecutionError as e:
    print(f"Task failed: {e.message}")
    print(f"Task ID: {e.task_id}")
    print(f"Agent ID: {e.agent_id}")
    
    # Retry with exponential backoff
    import asyncio
    for attempt in range(3):
        try:
            result = await orchestrator.execute_task(task)
            break
        except TaskExecutionError:
            await asyncio.sleep(2 ** attempt)
```

**Debugging Steps**
1. Verify agent status
2. Check task format
3. Review task logs
4. Test with simple task first
5. Check resource usage

---

## Error Messages

### OrchestratorInitializationError

**Message**: "Failed to initialize orchestrator"  
**Cause**: Orchestrator initialization failed  
**Solution**: Check configuration and dependencies

### AgentNotFoundError

**Message**: "Agent 'agent-id' not found"  
**Cause**: Agent is not registered  
**Solution**: Register agent before use

### CoordinationError

**Message**: "Coordination failed"  
**Cause**: Multi-agent coordination failed  
**Solution**: Check agent count and timeout

### TaskExecutionError

**Message**: "Task execution failed"  
**Cause**: Task execution failed  
**Solution**: Check task format and agent status

### EthicsValidationError

**Message**: "Ethics validation failed: violation_type"  
**Cause**: Operation violates ethics constraints  
**Solution**: Review ethics guidelines

### ConfigurationError

**Message**: "Invalid configuration for 'key': value"  
**Cause**: Configuration value is invalid  
**Solution**: Fix configuration value

---

## Debugging Techniques

### Enable Debug Logging

```python
import logging

# Set logging level to DEBUG
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("helix_orchestration")
logger.setLevel(logging.DEBUG)

# Add file handler
handler = logging.FileHandler("orchestration.log")
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)
```

### Use Verbose Output

```python
# Enable verbose output
import sys

class VerboseOrchestrator:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
    
    async def execute_task(self, task):
        print(f"Executing task: {task['id']}")
        result = await self.orchestrator.execute_task(task)
        print(f"Task result: {result['status']}")
        return result
```

### Profile Code

```python
import cProfile
import pstats

# Profile orchestration
profiler = cProfile.Profile()
profiler.enable()

# Run orchestration
await orchestrator.coordinate()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats("cumulative")
stats.print_stats(20)
```

### Monitor Resources

```python
import psutil
import time

process = psutil.Process()

# Monitor memory
while True:
    memory = process.memory_info().rss / 1024 / 1024
    print(f"Memory: {memory:.2f} MB")
    time.sleep(1)
```

---

## Performance Issues

### Issue: Slow Coordination

**Symptoms**
- Coordination takes > 1 second
- System is slow
- High CPU usage

**Debugging**

```python
import time

# Measure coordination time
start = time.time()
result = await orchestrator.coordinate()
elapsed = time.time() - start

print(f"Coordination time: {elapsed:.3f}s")

# If slow, check:
# 1. Agent count
# 2. System load
# 3. Network latency
# 4. Timeout settings
```

**Solutions**
1. Reduce agent count
2. Increase timeout
3. Optimize agent code
4. Use connection pooling

### Issue: High Memory Usage

**Symptoms**
- Memory usage > 1 GB
- System becomes slow
- Out of memory errors

**Debugging**

```python
import psutil

process = psutil.Process()
memory = process.memory_info().rss / 1024 / 1024
print(f"Memory usage: {memory:.2f} MB")

# Per agent: ~50-100 MB
# 18 agents: ~900-1800 MB
```

**Solutions**
1. Reduce agent count
2. Clear old metrics
3. Enable compression
4. Use streaming for large results

### Issue: Low Throughput

**Symptoms**
- Tasks per second < 100
- System is underutilized
- CPU usage < 50%

**Debugging**

```python
import time

# Measure throughput
start = time.time()
tasks = [orchestrator.execute_task(task) for task in task_list]
results = await asyncio.gather(*tasks)
elapsed = time.time() - start

throughput = len(results) / elapsed
print(f"Throughput: {throughput:.0f} tasks/sec")
```

**Solutions**
1. Increase agent count
2. Use batch operations
3. Enable connection pooling
4. Optimize task processing

---

## Integration Issues

### Issue: Agent Core Integration Fails

**Symptoms**
- Agent cores don't initialize
- Coordination fails with agent cores
- Type errors or import errors

**Solutions**

```python
# Verify agent core import
try:
    from helix_orchestration.coordination.gemini_core import GeminiCore
except ImportError as e:
    print(f"Import error: {e}")
    # Check if module exists
    # Verify Python path

# Test agent core directly
from helix_orchestration.coordination.gemini_core import GeminiCore

gemini = GeminiCore()
await gemini.initialize()
print(f"Gemini status: {gemini.status}")
```

### Issue: MCP Tool Integration Fails

**Symptoms**
- MCP tools not available
- Tool calls fail
- Integration errors

**Solutions**

```python
# Verify MCP tools are available
try:
    from helix_orchestration.agents.agent_orchestrator import RESONANCE_AVAILABLE
    print(f"Resonance Engine available: {RESONANCE_AVAILABLE}")
except ImportError as e:
    print(f"MCP integration error: {e}")

# Check MCP configuration
# Verify MCP server is running
# Check network connectivity
```

---

## FAQ

### Q: How do I increase the maximum agent count?

**A**: Modify the `max_agents` parameter:

```python
orchestrator = AgentOrchestrator(max_agents=30)
```

However, note that performance may degrade with > 18 agents.

### Q: How do I monitor orchestration metrics?

**A**: Use the metrics API:

```python
metrics = await orchestrator.get_metrics()
print(f"Active agents: {metrics.active_agents}")
print(f"Consensus: {metrics.consensus}")
print(f"UCF metrics: {metrics.ucf}")
```

### Q: How do I handle agent failures?

**A**: Use error handling and retry logic:

```python
from helix_orchestration.exceptions import TaskExecutionError

for attempt in range(3):
    try:
        result = await orchestrator.execute_task(task)
        break
    except TaskExecutionError as e:
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)
        else:
            raise
```

### Q: How do I optimize performance?

**A**: Follow these recommendations:

1. Use connection pooling
2. Batch operations
3. Enable caching
4. Monitor metrics
5. Profile code
6. Reduce agent count if needed

### Q: How do I debug coordination issues?

**A**: Enable debug logging and monitor metrics:

```python
logging.basicConfig(level=logging.DEBUG)

# Monitor coordination
result = await orchestrator.coordinate()
print(f"Coordination result: {result}")

# Check metrics
metrics = await orchestrator.get_metrics()
print(f"Metrics: {metrics}")
```

### Q: What's the maximum number of agents?

**A**: The system supports up to 18 agents. Beyond that, consider using multiple orchestrator instances.

### Q: How do I gracefully shutdown?

**A**: Use the shutdown method:

```python
await orchestrator.shutdown()
```

This will cleanly shutdown all agents and free resources.

---

## Getting Help

If you encounter issues not covered here:

1. Check the [API Reference](API_REFERENCE.md)
2. Review the [Performance Guide](PERFORMANCE.md)
3. Check the [Examples](../examples/)
4. Review logs for error details
5. Open an issue on GitHub

---

**Last Updated**: April 2, 2026  
**Status**: Production Ready
