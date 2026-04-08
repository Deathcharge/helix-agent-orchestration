"""
Test Suite for Workflows Module
================================

Comprehensive tests for workflow templates and communication patterns.
"""

import pytest
import asyncio
from helix_orchestration.workflows import (
    WorkflowTemplate,
    WorkflowStep,
    CommunicationPattern,
    WorkflowTemplateLibrary,
    CommunicationPatternHandler,
    WorkflowComposer,
)


class TestWorkflowStep:
    """Test workflow steps"""
    
    def test_create_workflow_step(self):
        """Test creating a workflow step"""
        step = WorkflowStep(
            name="process_data",
            agent_id="processor",
            action="process",
            parameters={"format": "json"}
        )
        
        assert step.name == "process_data"
        assert step.agent_id == "processor"
        assert step.action == "process"
        assert step.timeout == 30
        assert step.retry_count == 3
    
    def test_workflow_step_with_dependencies(self):
        """Test workflow step with dependencies"""
        step = WorkflowStep(
            name="analyze",
            agent_id="analyzer",
            action="analyze",
            dependencies=["validate", "transform"]
        )
        
        assert len(step.dependencies) == 2
        assert "validate" in step.dependencies


class TestWorkflowTemplate:
    """Test workflow templates"""
    
    def test_create_workflow_template(self):
        """Test creating a workflow template"""
        steps = [
            WorkflowStep(name="step1", agent_id="agent1", action="action1"),
            WorkflowStep(name="step2", agent_id="agent2", action="action2", dependencies=["step1"]),
        ]
        
        template = WorkflowTemplate(
            name="Test Workflow",
            description="A test workflow",
            pattern=CommunicationPattern.PIPELINE,
            steps=steps
        )
        
        assert template.name == "Test Workflow"
        assert len(template.steps) == 2
        assert template.pattern == CommunicationPattern.PIPELINE
    
    def test_validate_workflow_no_cycles(self):
        """Test validating workflow without cycles"""
        steps = [
            WorkflowStep(name="step1", agent_id="agent1", action="action1"),
            WorkflowStep(name="step2", agent_id="agent2", action="action2", dependencies=["step1"]),
            WorkflowStep(name="step3", agent_id="agent3", action="action3", dependencies=["step2"]),
        ]
        
        template = WorkflowTemplate(
            name="Valid Workflow",
            description="Valid workflow",
            pattern=CommunicationPattern.PIPELINE,
            steps=steps
        )
        
        assert template.validate() is True
    
    def test_validate_workflow_with_cycles(self):
        """Test validating workflow with cycles"""
        steps = [
            WorkflowStep(name="step1", agent_id="agent1", action="action1", dependencies=["step2"]),
            WorkflowStep(name="step2", agent_id="agent2", action="action2", dependencies=["step1"]),
        ]
        
        template = WorkflowTemplate(
            name="Invalid Workflow",
            description="Invalid workflow with cycle",
            pattern=CommunicationPattern.PIPELINE,
            steps=steps
        )
        
        assert template.validate() is False


class TestWorkflowTemplateLibrary:
    """Test workflow template library"""
    
    def test_data_processing_pipeline(self):
        """Test data processing pipeline template"""
        template = WorkflowTemplateLibrary.data_processing_pipeline()
        
        assert template.name == "Data Processing Pipeline"
        assert len(template.steps) == 4
        assert template.validate() is True
    
    def test_content_generation_workflow(self):
        """Test content generation workflow template"""
        template = WorkflowTemplateLibrary.content_generation_workflow()
        
        assert template.name == "Content Generation Workflow"
        assert len(template.steps) == 5
        assert template.validate() is True
    
    def test_decision_making_workflow(self):
        """Test decision making workflow template"""
        template = WorkflowTemplateLibrary.decision_making_workflow()
        
        assert template.name == "Decision Making Workflow"
        assert template.pattern == CommunicationPattern.CONSENSUS
        assert template.validate() is True
    
    def test_distributed_processing_workflow(self):
        """Test distributed processing workflow template"""
        template = WorkflowTemplateLibrary.distributed_processing_workflow()
        
        assert template.name == "Distributed Processing Workflow"
        assert template.pattern == CommunicationPattern.MAP_REDUCE
        assert template.validate() is True
    
    def test_error_recovery_workflow(self):
        """Test error recovery workflow template"""
        template = WorkflowTemplateLibrary.error_recovery_workflow()
        
        assert template.name == "Error Recovery Workflow"
        assert len(template.steps) >= 3
        assert template.validate() is True
    
    def test_hierarchical_approval_workflow(self):
        """Test hierarchical approval workflow template"""
        template = WorkflowTemplateLibrary.hierarchical_approval_workflow()
        
        assert template.name == "Hierarchical Approval Workflow"
        assert template.pattern == CommunicationPattern.HIERARCHICAL
        assert template.validate() is True
    
    def test_monitoring_workflow(self):
        """Test monitoring and alerting workflow template"""
        template = WorkflowTemplateLibrary.monitoring_and_alerting_workflow()
        
        assert template.name == "Monitoring and Alerting Workflow"
        assert template.pattern == CommunicationPattern.BROADCAST
        assert template.validate() is True


class TestCommunicationPatterns:
    """Test communication patterns"""
    
    @pytest.mark.asyncio
    async def test_broadcast_pattern(self):
        """Test broadcast communication pattern"""
        result = await CommunicationPatternHandler.broadcast(
            "sender",
            ["agent1", "agent2", "agent3"],
            {"message": "Hello"}
        )
        
        assert len(result) == 3
        assert "agent1" in result
        assert "agent2" in result
        assert "agent3" in result
    
    @pytest.mark.asyncio
    async def test_consensus_pattern(self):
        """Test consensus communication pattern"""
        result = await CommunicationPatternHandler.consensus(
            ["agent1", "agent2", "agent3"],
            {"question": "Should we proceed?"},
            threshold=0.8
        )
        
        assert "consensus_reached" in result
        assert "agreement_ratio" in result
        assert 0 <= result["agreement_ratio"] <= 1
    
    @pytest.mark.asyncio
    async def test_pipeline_pattern(self):
        """Test pipeline communication pattern"""
        steps = [
            WorkflowStep(name="step1", agent_id="agent1", action="action1"),
            WorkflowStep(name="step2", agent_id="agent2", action="action2", dependencies=["step1"]),
        ]
        
        result = await CommunicationPatternHandler.pipeline(
            steps,
            {"initial": "data"}
        )
        
        assert "step1" in result
        assert "step2" in result
    
    @pytest.mark.asyncio
    async def test_map_reduce_pattern(self):
        """Test map-reduce communication pattern"""
        partitions = [
            {"partition": 1, "data": [1, 2, 3]},
            {"partition": 2, "data": [4, 5, 6]},
        ]
        
        result = await CommunicationPatternHandler.map_reduce(
            partitions,
            ["worker1", "worker2"],
            "aggregator"
        )
        
        assert "status" in result


class TestWorkflowComposer:
    """Test workflow composition"""
    
    def test_create_custom_workflow(self):
        """Test creating custom workflow"""
        composer = WorkflowComposer()
        
        steps = [
            WorkflowStep(name="step1", agent_id="agent1", action="action1"),
            WorkflowStep(name="step2", agent_id="agent2", action="action2", dependencies=["step1"]),
        ]
        
        workflow = composer.create_custom_workflow(
            "Custom Workflow",
            CommunicationPattern.PIPELINE,
            steps
        )
        
        assert workflow.name == "Custom Workflow"
        assert len(workflow.steps) == 2
    
    def test_combine_workflows(self):
        """Test combining workflows"""
        composer = WorkflowComposer()
        
        workflow1 = WorkflowTemplateLibrary.data_processing_pipeline()
        workflow2 = WorkflowTemplateLibrary.error_recovery_workflow()
        
        combined = composer.combine_workflows(
            "Combined Workflow",
            [workflow1, workflow2],
            CommunicationPattern.PIPELINE
        )
        
        assert combined.name == "Combined Workflow"
        assert len(combined.steps) > len(workflow1.steps)


class TestWorkflowIntegration:
    """Integration tests for workflows"""
    
    def test_complete_workflow_execution(self):
        """Test complete workflow execution"""
        library = WorkflowTemplateLibrary()
        
        # Get different templates
        templates = [
            library.data_processing_pipeline(),
            library.content_generation_workflow(),
            library.decision_making_workflow(),
        ]
        
        # Validate all templates
        for template in templates:
            assert template.validate() is True
            assert len(template.steps) > 0
    
    @pytest.mark.asyncio
    async def test_workflow_with_communication_pattern(self):
        """Test workflow with communication pattern"""
        template = WorkflowTemplateLibrary.distributed_processing_workflow()
        
        # Validate workflow
        assert template.validate() is True
        
        # Execute with pattern handler
        partitions = [
            {"partition": 1},
            {"partition": 2},
            {"partition": 3},
            {"partition": 4},
        ]
        
        result = await CommunicationPatternHandler.map_reduce(
            partitions,
            ["worker1", "worker2", "worker3", "worker4"],
            "aggregator"
        )
        
        assert result is not None
