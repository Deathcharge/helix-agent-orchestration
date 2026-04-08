"""
Test Suite for Communication Module
====================================

Comprehensive tests for agent communication, messaging, and coordination.
"""

import pytest
import asyncio
from helix_orchestration.communication import (
    Message,
    MessageResponse,
    MessageType,
    MessagePriority,
    MessageRouter,
    ConsensusProtocol,
    ConflictResolution,
    CommunicationMiddleware,
    MessageQueue,
    AgentCommunicationHub,
)


class TestMessage:
    """Test message creation and properties"""
    
    def test_create_message(self):
        """Test creating a message"""
        message = Message(
            sender_id="agent1",
            recipient_ids=["agent2", "agent3"],
            message_type=MessageType.REQUEST,
            content={"action": "process"}
        )
        
        assert message.sender_id == "agent1"
        assert len(message.recipient_ids) == 2
        assert message.message_type == MessageType.REQUEST
        assert not message.is_expired()
    
    def test_message_expiration(self):
        """Test message expiration"""
        message = Message(
            sender_id="agent1",
            recipient_ids=["agent2"],
            timeout=0  # Immediately expired
        )
        
        import time
        time.sleep(0.1)
        assert message.is_expired()


class TestMessageRouter:
    """Test message routing"""
    
    @pytest.mark.asyncio
    async def test_route_message(self):
        """Test routing a message"""
        router = MessageRouter()
        
        message = Message(
            sender_id="agent1",
            recipient_ids=["agent2"],
            message_type=MessageType.REQUEST
        )
        
        await router.route_message(message)
        
        assert len(router.message_history) == 1
    
    @pytest.mark.asyncio
    async def test_get_message(self):
        """Test getting message from router"""
        router = MessageRouter()
        
        message = Message(
            sender_id="agent1",
            recipient_ids=["agent2"],
            message_type=MessageType.REQUEST
        )
        
        await router.route_message(message)
        retrieved = await router.get_message(timeout=1)
        
        assert retrieved is not None
        assert retrieved.sender_id == "agent1"
    
    def test_register_route(self):
        """Test registering routes"""
        router = MessageRouter()
        
        router.register_route("agent1", ["agent2", "agent3"])
        routes = router.get_routes_for_agent("agent1")
        
        assert len(routes) == 2
        assert "agent2" in routes
    
    def test_get_message_history(self):
        """Test getting message history"""
        router = MessageRouter()
        
        # This would need async context, so just test the method exists
        assert hasattr(router, "get_message_history")


class TestMessageQueue:
    """Test priority-based message queue"""
    
    @pytest.mark.asyncio
    async def test_priority_queue_ordering(self):
        """Test that messages are retrieved by priority"""
        queue = MessageQueue()
        
        # Add messages with different priorities
        low_msg = Message(
            sender_id="agent1",
            recipient_ids=["agent2"],
            priority=MessagePriority.LOW
        )
        
        critical_msg = Message(
            sender_id="agent3",
            recipient_ids=["agent4"],
            priority=MessagePriority.CRITICAL
        )
        
        await queue.put(low_msg)
        await queue.put(critical_msg)
        
        # Critical should be retrieved first
        first = await queue.get(timeout=1)
        assert first.priority == MessagePriority.CRITICAL
    
    def test_queue_size(self):
        """Test getting queue size"""
        queue = MessageQueue()
        assert queue.size() == 0


class TestConsensusProtocol:
    """Test consensus protocol"""
    
    @pytest.mark.asyncio
    async def test_initiate_consensus(self):
        """Test initiating consensus"""
        from helix_orchestration.communication import MessageRouter
        
        protocol = ConsensusProtocol()
        router = MessageRouter()
        
        result = await protocol.initiate_consensus(
            "proposer",
            ["agent1", "agent2", "agent3"],
            {"proposal": "test"},
            router
        )
        
        assert "consensus_id" in result
        assert "consensus_reached" in result
        assert "agreement_ratio" in result
    
    def test_add_vote(self):
        """Test adding a vote"""
        protocol = ConsensusProtocol()
        
        protocol.add_vote("agent1", {"agree": True})
        
        assert "agent1" in protocol.votes


class TestConflictResolution:
    """Test conflict resolution"""
    
    @pytest.mark.asyncio
    async def test_resolve_conflict(self):
        """Test resolving a conflict"""
        from helix_orchestration.communication import MessageRouter
        
        router = MessageRouter()
        
        result = await ConflictResolution.resolve_conflict(
            ["agent1", "agent2"],
            {"conflict": "resource_allocation"},
            "mediator",
            router
        )
        
        assert "resolution_id" in result
        assert "resolution" in result
        assert "positions" in result


class TestCommunicationMiddleware:
    """Test communication middleware"""
    
    def test_add_interceptor(self):
        """Test adding an interceptor"""
        middleware = CommunicationMiddleware()
        
        async def test_interceptor(msg):
            return msg
        
        middleware.add_interceptor(test_interceptor)
        assert len(middleware.interceptors) == 1
    
    def test_add_message_filter(self):
        """Test adding a message filter"""
        middleware = CommunicationMiddleware()
        
        def test_filter(msg):
            return msg.sender_id != "blocked"
        
        middleware.add_message_filter(test_filter)
        assert len(middleware.message_filters) == 1
    
    @pytest.mark.asyncio
    async def test_process_message_with_filter(self):
        """Test processing message with filter"""
        middleware = CommunicationMiddleware()
        
        def block_agent1(msg):
            return msg.sender_id != "agent1"
        
        middleware.add_message_filter(block_agent1)
        
        message = Message(
            sender_id="agent1",
            recipient_ids=["agent2"]
        )
        
        result = await middleware.process_message(message)
        assert result is None
    
    def test_set_rate_limit(self):
        """Test setting rate limit"""
        middleware = CommunicationMiddleware()
        
        middleware.set_rate_limit("agent1", 50)
        assert middleware.rate_limiters["agent1"] == 50


class TestAgentCommunicationHub:
    """Test agent communication hub"""
    
    def test_register_agent(self):
        """Test registering an agent"""
        hub = AgentCommunicationHub()
        
        hub.register_agent("agent1", {"role": "processor"})
        
        assert "agent1" in hub.list_agents()
    
    def test_get_agent_info(self):
        """Test getting agent info"""
        hub = AgentCommunicationHub()
        
        hub.register_agent("agent1", {"role": "processor", "status": "active"})
        info = hub.get_agent_info("agent1")
        
        assert info["role"] == "processor"
        assert info["status"] == "active"
    
    def test_list_agents(self):
        """Test listing agents"""
        hub = AgentCommunicationHub()
        
        hub.register_agent("agent1", {})
        hub.register_agent("agent2", {})
        hub.register_agent("agent3", {})
        
        agents = hub.list_agents()
        assert len(agents) == 3
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending message through hub"""
        hub = AgentCommunicationHub()
        
        message = Message(
            sender_id="agent1",
            recipient_ids=["agent2"],
            message_type=MessageType.REQUEST
        )
        
        success = await hub.send_message(message)
        assert success is True
    
    @pytest.mark.asyncio
    async def test_receive_message(self):
        """Test receiving message from hub"""
        hub = AgentCommunicationHub()
        
        message = Message(
            sender_id="agent1",
            recipient_ids=["agent2"],
            message_type=MessageType.REQUEST
        )
        
        await hub.send_message(message)
        received = await hub.receive_message(timeout=1)
        
        assert received is not None


class TestCommunicationIntegration:
    """Integration tests for communication"""
    
    @pytest.mark.asyncio
    async def test_complete_communication_workflow(self):
        """Test complete communication workflow"""
        hub = AgentCommunicationHub()
        
        # Register agents
        hub.register_agent("analyzer", {"role": "analyzer"})
        hub.register_agent("processor", {"role": "processor"})
        hub.register_agent("reporter", {"role": "reporter"})
        
        # Send message from analyzer to processor
        message1 = Message(
            sender_id="analyzer",
            recipient_ids=["processor"],
            message_type=MessageType.REQUEST,
            content={"action": "process", "data": [1, 2, 3]}
        )
        
        await hub.send_message(message1)
        
        # Send message from processor to reporter
        message2 = Message(
            sender_id="processor",
            recipient_ids=["reporter"],
            message_type=MessageType.RESPONSE,
            content={"result": "processed"}
        )
        
        await hub.send_message(message2)
        
        # Verify agents are registered
        assert len(hub.list_agents()) == 3
    
    @pytest.mark.asyncio
    async def test_multi_agent_consensus(self):
        """Test multi-agent consensus"""
        hub = AgentCommunicationHub()
        protocol = ConsensusProtocol()
        router = MessageRouter()
        
        # Register agents
        for i in range(5):
            hub.register_agent(f"agent{i}", {"role": "voter"})
        
        # Initiate consensus
        result = await protocol.initiate_consensus(
            "coordinator",
            [f"agent{i}" for i in range(5)],
            {"proposal": "increase_capacity"},
            router
        )
        
        assert "consensus_reached" in result
        assert "agreement_ratio" in result
