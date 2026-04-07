"""
Advanced Patterns and Use Cases

Demonstrates advanced usage patterns for helix-agent-orchestration
including monitoring, caching, resilience, and plugin systems.
"""

import asyncio
from helix_orchestration.monitoring.observability import (
    ObservabilityManager,
    Metric,
    MetricType,
)
from helix_orchestration.monitoring.tracing import DistributedTracer, SpanContextManager
from helix_orchestration.config.advanced_config import (
    ConfigurationManager,
    ConfigProfile,
)
from helix_orchestration.optimization.cache import CacheManager, EvictionPolicy
from helix_orchestration.resilience.patterns import (
    RetryPolicy,
    CircuitBreaker,
    RateLimiter,
    ResilienceManager,
)
from helix_orchestration.debugging.logger import DiagnosticCollector


async def example_monitoring_and_observability():
    """Example: Comprehensive monitoring and observability."""
    print("\n=== Monitoring and Observability Example ===")
    
    observability = ObservabilityManager()
    
    # Register health checks
    async def check_orchestrator_health():
        return True
    
    observability.health_checker.register_check("orchestrator", check_orchestrator_health)
    
    # Collect metrics
    metric = Metric(
        name="agent_registration_time",
        value=45.5,
        metric_type=MetricType.HISTOGRAM,
        labels={"agent_type": "gemini"},
    )
    await observability.metrics_collector.record_metric(metric)
    
    # Get system overview
    overview = await observability.get_system_overview()
    print(f"System Status: {overview['overall_status']}")
    print(f"Health Checks: {len(overview['health_checks'])}")
    
    # Get performance report
    performance = await observability.get_performance_report()
    print(f"Performance Data: {len(performance)} operations tracked")


async def example_distributed_tracing():
    """Example: Distributed tracing across operations."""
    print("\n=== Distributed Tracing Example ===")
    
    tracer = DistributedTracer()
    
    # Start a trace
    trace_id = tracer.start_trace()
    print(f"Started trace: {trace_id}")
    
    # Create nested spans
    span1_id = tracer.start_span("agent_initialization", trace_id=trace_id)
    tracer.add_span_tag(span1_id, "agent_type", "gemini")
    tracer.add_span_log(span1_id, "Agent initialized successfully")
    
    # Simulate nested operation
    span2_id = tracer.start_span(
        "coordination_setup",
        trace_id=trace_id,
        parent_span_id=span1_id,
    )
    tracer.add_span_tag(span2_id, "agents_count", 3)
    tracer.end_span(span2_id)
    
    tracer.end_span(span1_id)
    
    # End trace and get tree
    trace = tracer.end_trace(trace_id)
    print(f"Trace completed: {trace.duration_ms:.2f}ms")
    
    # Get trace tree
    tree = tracer.get_trace_tree(trace_id)
    print(f"Trace spans: {len(tree['children']) if tree else 0}")


async def example_advanced_configuration():
    """Example: Advanced configuration management."""
    print("\n=== Advanced Configuration Example ===")
    
    # Create configuration manager
    config_manager = ConfigurationManager(profile=ConfigProfile.PRODUCTION)
    
    # Validate configuration
    if config_manager.validate():
        print("✓ Configuration is valid")
    
    # Update configuration
    config_manager.update_orchestrator_config(max_agents=20, log_level="DEBUG")
    config_manager.update_caching_config(enable_caching=True, cache_ttl=600)
    
    # Export configuration
    config_dict = config_manager.export_to_dict()
    print(f"Configuration profile: {config_dict['profile']}")
    print(f"Max agents: {config_dict['orchestrator']['max_agents']}")
    print(f"Cache TTL: {config_dict['caching']['cache_ttl']}")


async def example_caching_strategies():
    """Example: Caching with different strategies."""
    print("\n=== Caching Strategies Example ===")
    
    # Create cache manager with LRU eviction
    cache_manager = CacheManager(
        max_size=100,
        eviction_policy=EvictionPolicy.LRU,
        enable_compression=True,
    )
    
    # Create namespace for agent data
    await cache_manager.create_namespace("agents", max_size=50)
    
    # Cache some data
    agent_data = {"id": "agent_1", "type": "gemini", "status": "active"}
    await cache_manager.set("agent_1", agent_data, ttl=300, namespace="agents")
    
    # Retrieve from cache
    cached = await cache_manager.get("agent_1", namespace="agents")
    print(f"Cached agent: {cached}")
    
    # Get cache statistics
    stats = await cache_manager.get_stats()
    print(f"Cache stats - Main: {stats['main']['hit_rate']:.1f}% hit rate")


async def example_resilience_patterns():
    """Example: Resilience patterns."""
    print("\n=== Resilience Patterns Example ===")
    
    resilience = ResilienceManager()
    
    # Example function that might fail
    attempt_count = 0
    
    async def unstable_operation():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise Exception(f"Attempt {attempt_count} failed")
        return "Success!"
    
    # Execute with retry
    retry_policy = RetryPolicy()
    try:
        result = await retry_policy.execute_with_retry(unstable_operation)
        print(f"Operation result: {result}")
    except Exception as e:
        print(f"Operation failed: {e}")
    
    # Get resilience statistics
    stats = await resilience.get_resilience_stats()
    print(f"Circuit breaker state: {stats['circuit_breaker']['state']}")


async def example_advanced_logging():
    """Example: Advanced logging and diagnostics."""
    print("\n=== Advanced Logging Example ===")
    
    diagnostics = DiagnosticCollector()
    
    # Log messages with context
    diagnostics.logger.info(
        "Agent initialized",
        agent_id="agent_1",
        agent_type="gemini",
        status="active",
    )
    
    diagnostics.logger.warning(
        "High latency detected",
        operation="coordination",
        latency_ms=250,
        threshold_ms=200,
    )
    
    # Enable debug mode
    diagnostics.debug_mode.enable(verbose=True)
    diagnostics.debug_mode.watch("active_agents", 5)
    
    # Collect diagnostics
    diag_data = await diagnostics.collect_diagnostics()
    print(f"Debug enabled: {diag_data['debug_enabled']}")
    print(f"Recent logs: {len(diag_data['recent_logs'])} entries")
    print(f"Watches: {diag_data['watches']}")


async def example_rate_limiting():
    """Example: Rate limiting."""
    print("\n=== Rate Limiting Example ===")
    
    rate_limiter = RateLimiter(requests=10, window=60)
    
    # Simulate requests
    successful = 0
    failed = 0
    
    for i in range(15):
        if await rate_limiter.acquire():
            successful += 1
        else:
            failed += 1
    
    print(f"Successful requests: {successful}")
    print(f"Rate limited requests: {failed}")


async def example_circuit_breaker():
    """Example: Circuit breaker pattern."""
    print("\n=== Circuit Breaker Example ===")
    
    circuit_breaker = CircuitBreaker()
    
    # Simulate failing operation
    async def failing_operation():
        raise Exception("Service unavailable")
    
    # Try to call through circuit breaker
    for i in range(10):
        try:
            await circuit_breaker.call(failing_operation)
        except Exception as e:
            print(f"Attempt {i+1}: {str(e)[:30]}...")
        
        if circuit_breaker.state.value == "open":
            print(f"Circuit breaker opened after {i+1} failures")
            break


async def example_comprehensive_workflow():
    """Example: Comprehensive workflow using multiple features."""
    print("\n=== Comprehensive Workflow Example ===")
    
    # Setup components
    config_manager = ConfigurationManager(profile=ConfigProfile.PRODUCTION)
    observability = ObservabilityManager()
    tracer = DistributedTracer()
    cache_manager = CacheManager()
    diagnostics = DiagnosticCollector()
    
    # Start trace
    trace_id = tracer.start_trace()
    
    # Simulate orchestration workflow
    with_span = SpanContextManager(tracer, "orchestration_workflow")
    
    async with with_span as span_id:
        # Log start
        diagnostics.logger.info("Starting orchestration workflow", trace_id=trace_id)
        
        # Record metric
        metric = Metric(
            name="workflow_start",
            value=1,
            metric_type=MetricType.COUNTER,
        )
        await observability.metrics_collector.record_metric(metric)
        
        # Cache workflow state
        state = {"status": "running", "agents": 3}
        await cache_manager.set("workflow_state", state, ttl=300)
        
        # Simulate work
        await asyncio.sleep(0.1)
        
        # Record completion
        metric = Metric(
            name="workflow_complete",
            value=1,
            metric_type=MetricType.COUNTER,
        )
        await observability.metrics_collector.record_metric(metric)
        
        diagnostics.logger.info("Workflow completed successfully")
    
    # Get final statistics
    print(f"Trace ID: {trace_id}")
    print(f"Configuration valid: {config_manager.validate()}")
    print(f"Cache size: {(await cache_manager.get_stats())['main']['size']}")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("ADVANCED HELIX-AGENT-ORCHESTRATION EXAMPLES")
    print("=" * 60)
    
    await example_monitoring_and_observability()
    await example_distributed_tracing()
    await example_advanced_configuration()
    await example_caching_strategies()
    await example_resilience_patterns()
    await example_advanced_logging()
    await example_rate_limiting()
    await example_circuit_breaker()
    await example_comprehensive_workflow()
    
    print("\n" + "=" * 60)
    print("ALL EXAMPLES COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
