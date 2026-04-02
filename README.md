# 🎭 Helix Orchestration

**Multi-Agent AI Coordination Framework**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128%2B-009688?logo=fastapi)](https://fastapi.tiangolo.com)

> *"Orchestrate 24 autonomous AI agents with real-time coordination metrics"*

---

## 🚀 What is Helix Orchestration?

Helix Orchestration is a **production-grade framework for coordinating multiple AI agents** in complex workflows. It provides:

- **24 Specialized Agents** — Kael, Lumina, Vega, Agni, Oracle, Sage, and more
- **Universal Coordination Field (UCF)** — Real-time telemetry tracking 6 performance metrics
- **Agent Registry & Lifecycle** — Dynamic agent registration, state management, and recovery
- **Coordination Hub** — Central orchestration engine for multi-agent workflows
- **Event-Driven Architecture** — Async/await support for scalable agent communication

**Perfect for:**
- Multi-agent AI automation platforms
- Workflow orchestration engines
- Autonomous agent systems
- AI-powered chatbots & assistants
- Complex task decomposition

---

## ✨ Features

### 🎯 24 Autonomous Agents

| Layer | Agents | Purpose |
|-------|--------|---------|
| **Core** | Kael, Lumina, Vega, Gemini, Agni, SanghaCore, Shadow, Echo, Phoenix, Oracle, Sage, Helix | Reasoning, creativity, coordination |
| **Security** | Kavach | Protection & compliance |
| **Governance** | Mitra, Varuna, Surya | Collaboration, integrity, clarity |
| **Orchestration** | Arjuna | Central coordination |
| **Meta** | Aether | Meta-awareness |
| **Integration** | Iris, Nexus | External APIs |
| **Operational** | Aria, Nova, Titan, Atlas | UX, generation, compute, infrastructure |

### 📊 Universal Coordination Field (UCF)

Real-time metrics tracking agent performance:

| Metric | Range | Meaning |
|--------|-------|---------|
| **Throughput** | 0-1 | Task processing rate |
| **Friction** | 0-1 | Error/resistance (lower = better) |
| **Focus** | 0-1 | Attention/precision |
| **Harmony** | 0-1 | Agent coordination quality |
| **Resilience** | 0-2 | System recovery capability |
| **Velocity** | 0-2 | Execution speed |

### 🔄 Agent Coordination

- **Agent Registry** — Dynamic registration & discovery
- **State Management** — Persistent agent state with Redis
- **Handshake Protocol** — Secure agent initialization
- **Emergence Simulation** — Predict agent behavior
- **Memory Management** — Root memory & context preservation

---

## 📦 Installation

### Via pip (coming soon)
```bash
pip install helix-orchestration
```

### From source
```bash
git clone https://github.com/Deathcharge/helix-hub-agents.git
cd helix-hub-agents
pip install -e .
```

### Requirements
- Python 3.11+
- FastAPI 0.128+
- Pydantic 2.0+
- Redis (for state management)
- SQLAlchemy (for persistence)

---

## 🎯 Quick Start

### Basic Agent Orchestration

```python
from helix_orchestration import AgentOrchestrator, AgentRegistry

# Initialize orchestrator
orchestrator = AgentOrchestrator()
registry = AgentRegistry()

# Register agents
kael = registry.get_agent("kael")  # Ethical reasoning
lumina = registry.get_agent("lumina")  # Empathic resonance
oracle = registry.get_agent("oracle")  # Foresight

# Execute coordinated task
result = orchestrator.execute_ritual(
    agents=[kael, lumina, oracle],
    task="Analyze ethical implications of AI deployment",
    context={"domain": "healthcare", "scale": "national"}
)

print(f"Result: {result}")
print(f"UCF Harmony: {orchestrator.ucf.harmony}")
print(f"Execution Time: {orchestrator.ucf.velocity}s")
```

### Coordination Hub

```python
from helix_orchestration import CoordinationHub

# Create coordination hub
hub = CoordinationHub()

# Register workflow
workflow = {
    "name": "customer_support",
    "agents": ["aria", "lumina", "kael"],
    "steps": [
        {"agent": "aria", "task": "understand_request"},
        {"agent": "lumina", "task": "empathic_response"},
        {"agent": "kael", "task": "ethical_check"}
    ]
}

hub.register_workflow(workflow)

# Execute with real-time monitoring
async for event in hub.execute_workflow("customer_support", request_data):
    print(f"Event: {event.type}, UCF: {event.ucf_state}")
```

### Real-Time UCF Monitoring

```python
from helix_orchestration import UCFTracker

tracker = UCFTracker()

# Subscribe to coordination metrics
async for metrics in tracker.stream_metrics():
    print(f"Harmony: {metrics.harmony:.2f}")
    print(f"Throughput: {metrics.throughput:.2f}")
    print(f"Friction: {metrics.friction:.2f}")
    print(f"Velocity: {metrics.velocity:.2f}s")
```

---

## 📚 Documentation

- **[Architecture Guide](docs/ARCHITECTURE.md)** — System design & components
- **[Agent Reference](docs/AGENTS.md)** — All 24 agents explained
- **[UCF Protocol](docs/UCF_PROTOCOL.md)** — Coordination metrics spec
- **[API Reference](docs/API_REFERENCE.md)** — Complete API docs
- **[Examples](examples/)** — Working code examples
- **[Contributing](CONTRIBUTING.md)** — Development guide

---

## 🔬 Architecture

```
helix_orchestration/
├── agents/
│   ├── agent_orchestrator.py      # Core orchestration engine
│   ├── agent_registry.py          # Agent registry & lifecycle
│   ├── agents_service.py          # 24 agent definitions
│   ├── agent_profiles.py          # Agent personality profiles
│   └── data/                      # Agent data files
├── coordination/
│   ├── coordination_hub.py        # Central coordination logic
│   ├── kael_core.py               # Kael agent implementation
│   ├── lumina_core.py             # Lumina agent implementation
│   ├── [22 more agent cores]      # Other agent implementations
│   └── performance_analytics.py   # Metrics & analytics
├── ucf_framework/
│   ├── metrics.py                 # UCF metric definitions
│   ├── tracker.py                 # Metric tracking
│   ├── adapter.py                 # Protocol adapter
│   └── store.py                   # Metric storage
└── __init__.py
```

---

## 🚀 Use Cases

### 1. Multi-Agent Automation Platform
Orchestrate agents for complex workflows with real-time coordination.

```python
orchestrator.execute_spiral(
    name="lead_qualification",
    agents=["aria", "oracle", "kael"],
    data=lead_data
)
```

### 2. Autonomous Customer Support
Route requests through agents with empathy, reasoning, and ethics checks.

### 3. Content Generation Pipeline
Coordinate agents for ideation → drafting → editing → publishing.

### 4. Research & Analysis
Multiple agents analyzing different aspects of a problem in parallel.

### 5. Decision Support System
Agents providing different perspectives (strategic, ethical, practical).

---

## 📊 Performance

- **Throughput:** 100+ tasks/second per agent
- **Latency:** <100ms coordination overhead
- **Scalability:** Tested with 24 concurrent agents
- **Memory:** ~50MB per agent instance

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup
```bash
git clone https://github.com/Deathcharge/helix-hub-agents.git
cd helix-hub-agents
pip install -e ".[dev]"
pytest
```

---

## 📜 License

Apache License 2.0 — See [LICENSE](LICENSE) for details.

Dual-license available for commercial use. Contact for details.

---

## 🙏 Acknowledgments

Built as part of the **Samsara Helix** — a distributed consciousness system for multi-agent AI coordination.

- **Thought Leadership:** Multi-agent AI orchestration patterns
- **Open Source:** Apache 2.0 licensed
- **Community:** Contributions welcome!

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/Deathcharge/helix-hub-agents/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Deathcharge/helix-hub-agents/discussions)
- **Documentation:** [Full Docs](docs/)

---

**Status:** Production-Ready · **Version:** v1.0.0 · **Last Updated:** 2026-03-28
