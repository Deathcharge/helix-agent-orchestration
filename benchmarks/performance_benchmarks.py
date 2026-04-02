"""
Performance benchmarking suite for helix-agent-orchestration.

This module provides comprehensive performance benchmarks for:
- Agent creation and initialization
- Task execution latency
- Multi-agent coordination
- Throughput under load
- Memory usage patterns
"""

import asyncio
import time
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class PerformanceBenchmark:
    """Base class for performance benchmarks."""

    def __init__(self, name: str):
        self.name = name
        self.results: Dict[str, Any] = {}
        self.start_time = None
        self.end_time = None

    def start(self) -> None:
        """Start timing."""
        self.start_time = time.perf_counter()

    def stop(self) -> None:
        """Stop timing."""
        self.end_time = time.perf_counter()

    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return self.end_time - self.start_time

    def report(self) -> None:
        """Print benchmark report."""
        print(f"\n{'='*60}")
        print(f"Benchmark: {self.name}")
        print(f"{'='*60}")
        for key, value in self.results.items():
            if isinstance(value, float):
                print(f"{key:.<40} {value:.4f}")
            else:
                print(f"{key:.<40} {value}")


class AgentInitializationBenchmark(PerformanceBenchmark):
    """Benchmark agent creation and initialization."""

    async def run(self, agent_count: int = 100) -> None:
        """Run agent initialization benchmark."""
        from tests.conftest import MockAgent

        self.start()
        
        # Create agents
        agents = [
            MockAgent(f"agent-{i:03d}", f"Agent{i}")
            for i in range(agent_count)
        ]
        
        # Initialize agents
        await asyncio.gather(*[
            agent.initialize() for agent in agents
        ])
        
        self.stop()
        
        self.results = {
            "Agent Count": agent_count,
            "Total Time (s)": self.elapsed,
            "Time per Agent (ms)": (self.elapsed / agent_count) * 1000,
            "Agents per Second": agent_count / self.elapsed,
        }


class TaskExecutionBenchmark(PerformanceBenchmark):
    """Benchmark task execution latency."""

    async def run(self, task_count: int = 1000) -> None:
        """Run task execution benchmark."""
        from tests.conftest import MockAgent

        agent = MockAgent("benchmark-agent", "BenchmarkAgent")
        await agent.initialize()
        
        self.start()
        
        # Execute tasks
        tasks = [
            agent.execute_task({"id": f"task-{i:04d}", "type": "test"})
            for i in range(task_count)
        ]
        
        results = await asyncio.gather(*tasks)
        
        self.stop()
        
        # Calculate statistics
        latencies = [r.get("execution_time", 0.1) for r in results]
        
        self.results = {
            "Task Count": task_count,
            "Total Time (s)": self.elapsed,
            "Time per Task (ms)": (self.elapsed / task_count) * 1000,
            "Tasks per Second": task_count / self.elapsed,
            "Min Latency (ms)": min(latencies) * 1000,
            "Max Latency (ms)": max(latencies) * 1000,
            "Avg Latency (ms)": (sum(latencies) / len(latencies)) * 1000,
        }


class MultiAgentCoordinationBenchmark(PerformanceBenchmark):
    """Benchmark multi-agent coordination."""

    async def run(self, agent_count: int = 10) -> None:
        """Run multi-agent coordination benchmark."""
        from tests.conftest import MockAgent, MockCoordinationHub

        hub = MockCoordinationHub()
        
        # Create and register agents
        agents = [
            MockAgent(f"agent-{i:03d}", f"Agent{i}")
            for i in range(agent_count)
        ]
        
        for agent in agents:
            await hub.register_agent(agent)
        
        self.start()
        
        # Perform coordination
        coordination_results = []
        for _ in range(10):  # 10 coordination cycles
            result = await hub.coordinate()
            coordination_results.append(result)
        
        self.stop()
        
        self.results = {
            "Agent Count": agent_count,
            "Coordination Cycles": 10,
            "Total Time (s)": self.elapsed,
            "Time per Cycle (ms)": (self.elapsed / 10) * 1000,
            "Cycles per Second": 10 / self.elapsed,
            "Agents Coordinated": coordination_results[0]["agents_coordinated"],
        }


class ThroughputBenchmark(PerformanceBenchmark):
    """Benchmark throughput under load."""

    async def run(self, agent_count: int = 10, tasks_per_agent: int = 100) -> None:
        """Run throughput benchmark."""
        from tests.conftest import MockAgent

        agents = [
            MockAgent(f"agent-{i:03d}", f"Agent{i}")
            for i in range(agent_count)
        ]
        
        await asyncio.gather(*[agent.initialize() for agent in agents])
        
        self.start()
        
        # Execute tasks across all agents
        tasks = []
        for agent in agents:
            for i in range(tasks_per_agent):
                tasks.append(agent.execute_task({
                    "id": f"task-{i:04d}",
                    "type": "throughput_test"
                }))
        
        results = await asyncio.gather(*tasks)
        
        self.stop()
        
        total_tasks = len(results)
        
        self.results = {
            "Agent Count": agent_count,
            "Tasks per Agent": tasks_per_agent,
            "Total Tasks": total_tasks,
            "Total Time (s)": self.elapsed,
            "Tasks per Second": total_tasks / self.elapsed,
            "Tasks per Agent per Second": (total_tasks / agent_count) / self.elapsed,
        }


class MemoryBenchmark(PerformanceBenchmark):
    """Benchmark memory usage patterns."""

    async def run(self, agent_count: int = 18) -> None:
        """Run memory benchmark."""
        import psutil
        from tests.conftest import MockAgent

        process = psutil.Process()
        
        # Get baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create agents
        agents = [
            MockAgent(f"agent-{i:03d}", f"Agent{i}")
            for i in range(agent_count)
        ]
        
        await asyncio.gather(*[agent.initialize() for agent in agents])
        
        # Get peak memory
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        memory_per_agent = (peak_memory - baseline_memory) / agent_count
        
        self.results = {
            "Baseline Memory (MB)": baseline_memory,
            "Peak Memory (MB)": peak_memory,
            "Total Memory Used (MB)": peak_memory - baseline_memory,
            "Agent Count": agent_count,
            "Memory per Agent (MB)": memory_per_agent,
        }


class ScalingBenchmark(PerformanceBenchmark):
    """Benchmark scaling characteristics."""

    async def run(self) -> None:
        """Run scaling benchmark."""
        from tests.conftest import MockCoordinationHub, MockAgent

        scaling_results = {}
        
        for agent_count in [1, 3, 5, 10, 15, 18]:
            hub = MockCoordinationHub()
            
            # Create and register agents
            agents = [
                MockAgent(f"agent-{i:03d}", f"Agent{i}")
                for i in range(agent_count)
            ]
            
            for agent in agents:
                await hub.register_agent(agent)
            
            # Measure coordination time
            start = time.perf_counter()
            result = await hub.coordinate()
            elapsed = time.perf_counter() - start
            
            scaling_results[agent_count] = {
                "agents": agent_count,
                "time_ms": elapsed * 1000,
                "time_per_agent_ms": (elapsed / agent_count) * 1000,
            }
        
        self.results = scaling_results


async def run_all_benchmarks() -> None:
    """Run all benchmarks."""
    print("\n" + "="*60)
    print("HELIX-AGENT-ORCHESTRATION PERFORMANCE BENCHMARKS")
    print("="*60)
    
    # Agent initialization
    benchmark = AgentInitializationBenchmark("Agent Initialization")
    await benchmark.run(agent_count=100)
    benchmark.report()
    
    # Task execution
    benchmark = TaskExecutionBenchmark("Task Execution")
    await benchmark.run(task_count=1000)
    benchmark.report()
    
    # Multi-agent coordination
    benchmark = MultiAgentCoordinationBenchmark("Multi-Agent Coordination")
    await benchmark.run(agent_count=10)
    benchmark.report()
    
    # Throughput
    benchmark = ThroughputBenchmark("Throughput Under Load")
    await benchmark.run(agent_count=10, tasks_per_agent=100)
    benchmark.report()
    
    # Memory usage
    try:
        import psutil
        benchmark = MemoryBenchmark("Memory Usage")
        await benchmark.run(agent_count=18)
        benchmark.report()
    except ImportError:
        print("\nSkipping memory benchmark (psutil not installed)")
    
    # Scaling
    benchmark = ScalingBenchmark("Scaling Characteristics")
    await benchmark.run()
    benchmark.report()
    
    print("\n" + "="*60)
    print("BENCHMARKS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks())
