"""
Basic Agent Orchestration Example

This example demonstrates the fundamental workflow for orchestrating
multiple agents using the helix-agent-orchestration system.

Key Concepts:
- Initializing the orchestrator
- Creating and registering agents
- Performing multi-agent coordination
- Executing tasks through the orchestrator
- Monitoring metrics
- Graceful shutdown
"""

import asyncio
import logging
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SimpleAgent:
    """A simple agent for demonstration purposes."""

    def __init__(self, agent_id: str, name: str, role: str):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.status = "created"
        self.tasks_completed = 0

    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = "initialized"
        logger.info(f"Agent {self.name} initialized")

    async def execute_task(self, task: dict) -> dict:
        """Execute a task."""
        logger.info(f"Agent {self.name} executing task {task['id']}")
        
        # Simulate task execution
        await asyncio.sleep(0.1)
        
        self.tasks_completed += 1
        
        return {
            "task_id": task["id"],
            "agent_id": self.agent_id,
            "status": "completed",
            "result": f"Task {task['id']} completed by {self.name}",
        }

    async def shutdown(self) -> None:
        """Shutdown the agent."""
        self.status = "shutdown"
        logger.info(f"Agent {self.name} shutdown")


class SimpleOrchestrator:
    """A simple orchestrator for demonstration purposes."""

    def __init__(self, max_agents: int = 18):
        self.max_agents = max_agents
        self.agents: dict[str, SimpleAgent] = {}
        self.status = "created"

    async def initialize(self) -> None:
        """Initialize the orchestrator."""
        self.status = "initialized"
        logger.info("Orchestrator initialized")

    async def register_agent(self, agent: SimpleAgent) -> None:
        """Register an agent."""
        if len(self.agents) >= self.max_agents:
            raise RuntimeError(f"Maximum agents ({self.max_agents}) reached")
        
        self.agents[agent.agent_id] = agent
        await agent.initialize()
        logger.info(f"Agent {agent.name} registered (total: {len(self.agents)})")

    async def coordinate(self) -> dict:
        """Perform multi-agent coordination."""
        logger.info(f"Coordinating {len(self.agents)} agents")
        
        # Simulate coordination
        await asyncio.sleep(0.2)
        
        return {
            "status": "success",
            "agents_coordinated": len(self.agents),
            "consensus": 0.85,
        }

    async def execute_task(self, task: dict) -> dict:
        """Execute a task through the orchestrator."""
        if not self.agents:
            raise RuntimeError("No agents registered")
        
        # Select first agent for task
        agent = list(self.agents.values())[0]
        result = await agent.execute_task(task)
        
        return result

    async def get_metrics(self) -> dict:
        """Get orchestration metrics."""
        total_tasks = sum(agent.tasks_completed for agent in self.agents.values())
        
        return {
            "active_agents": len(self.agents),
            "total_tasks_completed": total_tasks,
            "avg_tasks_per_agent": total_tasks / len(self.agents) if self.agents else 0,
        }

    async def shutdown(self) -> None:
        """Shutdown the orchestrator."""
        for agent in self.agents.values():
            await agent.shutdown()
        
        self.status = "shutdown"
        logger.info("Orchestrator shutdown")


async def basic_orchestration_example():
    """
    Demonstrate basic agent orchestration workflow.
    
    This example shows:
    1. Creating an orchestrator
    2. Creating and registering agents
    3. Performing coordination
    4. Executing tasks
    5. Monitoring metrics
    6. Graceful shutdown
    """
    
    logger.info("=" * 60)
    logger.info("BASIC ORCHESTRATION EXAMPLE")
    logger.info("=" * 60)
    
    # Step 1: Create orchestrator
    logger.info("\n[Step 1] Creating orchestrator...")
    orchestrator = SimpleOrchestrator(max_agents=18)
    await orchestrator.initialize()
    
    # Step 2: Create agents
    logger.info("\n[Step 2] Creating agents...")
    agents = [
        SimpleAgent("agent-001", "Gemini", "scout"),
        SimpleAgent("agent-002", "Kavach", "shield"),
        SimpleAgent("agent-003", "Agni", "fire"),
    ]
    
    # Step 3: Register agents
    logger.info("\n[Step 3] Registering agents...")
    for agent in agents:
        await orchestrator.register_agent(agent)
    
    # Step 4: Perform coordination
    logger.info("\n[Step 4] Performing coordination...")
    coordination_result = await orchestrator.coordinate()
    logger.info(f"Coordination result: {coordination_result}")
    
    # Step 5: Execute tasks
    logger.info("\n[Step 5] Executing tasks...")
    tasks = [
        {"id": "task-001", "type": "analysis", "data": "sample data"},
        {"id": "task-002", "type": "synthesis", "data": "sample data"},
        {"id": "task-003", "type": "validation", "data": "sample data"},
    ]
    
    for task in tasks:
        result = await orchestrator.execute_task(task)
        logger.info(f"Task result: {result}")
    
    # Step 6: Get metrics
    logger.info("\n[Step 6] Getting metrics...")
    metrics = await orchestrator.get_metrics()
    logger.info(f"Orchestration metrics:")
    for key, value in metrics.items():
        logger.info(f"  {key}: {value}")
    
    # Step 7: Shutdown
    logger.info("\n[Step 7] Shutting down...")
    await orchestrator.shutdown()
    
    logger.info("\n" + "=" * 60)
    logger.info("EXAMPLE COMPLETE")
    logger.info("=" * 60)


async def concurrent_task_execution_example():
    """
    Demonstrate concurrent task execution with multiple agents.
    
    This example shows how to execute multiple tasks concurrently
    across different agents.
    """
    
    logger.info("\n" + "=" * 60)
    logger.info("CONCURRENT TASK EXECUTION EXAMPLE")
    logger.info("=" * 60)
    
    # Setup
    orchestrator = SimpleOrchestrator()
    await orchestrator.initialize()
    
    # Create more agents for concurrent execution
    agents = [
        SimpleAgent(f"agent-{i:03d}", f"Agent{i}", f"role{i}")
        for i in range(5)
    ]
    
    for agent in agents:
        await orchestrator.register_agent(agent)
    
    logger.info(f"Registered {len(agents)} agents")
    
    # Create tasks
    tasks = [
        {"id": f"task-{i:03d}", "type": "processing"}
        for i in range(10)
    ]
    
    logger.info(f"Executing {len(tasks)} tasks concurrently...")
    
    # Execute tasks concurrently
    results = await asyncio.gather(*[
        orchestrator.execute_task(task) for task in tasks
    ])
    
    logger.info(f"Completed {len(results)} tasks")
    
    # Show results
    for result in results:
        logger.info(f"  {result['task_id']}: {result['status']}")
    
    # Cleanup
    await orchestrator.shutdown()
    
    logger.info("=" * 60)


async def error_handling_example():
    """
    Demonstrate error handling in orchestration.
    
    This example shows how to handle common errors that might
    occur during orchestration.
    """
    
    logger.info("\n" + "=" * 60)
    logger.info("ERROR HANDLING EXAMPLE")
    logger.info("=" * 60)
    
    orchestrator = SimpleOrchestrator(max_agents=2)
    await orchestrator.initialize()
    
    # Example 1: Register too many agents
    logger.info("\n[Example 1] Attempting to register too many agents...")
    try:
        for i in range(5):
            agent = SimpleAgent(f"agent-{i}", f"Agent{i}", "role")
            await orchestrator.register_agent(agent)
    except RuntimeError as e:
        logger.error(f"Error: {e}")
    
    # Example 2: Execute task with no agents
    logger.info("\n[Example 2] Attempting to execute task with no agents...")
    orchestrator2 = SimpleOrchestrator()
    await orchestrator2.initialize()
    
    try:
        result = await orchestrator2.execute_task({"id": "task-001"})
    except RuntimeError as e:
        logger.error(f"Error: {e}")
    
    # Cleanup
    await orchestrator.shutdown()
    await orchestrator2.shutdown()
    
    logger.info("=" * 60)


async def main():
    """Run all examples."""
    
    # Run basic orchestration example
    await basic_orchestration_example()
    
    # Run concurrent execution example
    await concurrent_task_execution_example()
    
    # Run error handling example
    await error_handling_example()


if __name__ == "__main__":
    asyncio.run(main())
