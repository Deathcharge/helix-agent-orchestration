"""
Test Suite for Monitoring Module
=================================

Comprehensive tests for metrics collection, performance analysis, and health monitoring.
"""

import pytest
from datetime import datetime, timedelta
from helix_orchestration.monitoring import (
    MetricsCollector,
    PerformanceAnalyzer,
    HealthMonitor,
    MetricsReporter,
    MetricType,
    AlertSeverity,
)


class TestMetricsCollector:
    """Test metrics collection"""
    
    def test_collector_initialization(self):
        """Test collector initialization"""
        collector = MetricsCollector()
        assert collector.window_size == 1000
        assert collector.retention_hours == 24
    
    def test_record_metric(self):
        """Test recording a metric"""
        collector = MetricsCollector()
        
        collector.record_metric(
            MetricType.THROUGHPUT,
            value=10.5,
            agent_id="agent_1"
        )
        
        metrics = collector.get_metrics(MetricType.THROUGHPUT, agent_id="agent_1")
        assert len(metrics) == 1
        assert metrics[0].value == 10.5
    
    def test_record_multiple_metrics(self):
        """Test recording multiple metrics"""
        collector = MetricsCollector()
        
        for i in range(100):
            collector.record_metric(
                MetricType.LATENCY,
                value=100 + i,
                agent_id="agent_1"
            )
        
        metrics = collector.get_metrics(MetricType.LATENCY, agent_id="agent_1")
        assert len(metrics) == 100
    
    def test_get_metrics_with_time_window(self):
        """Test getting metrics with time window"""
        collector = MetricsCollector()
        
        # Record old metric
        old_point = collector.record_metric(
            MetricType.THROUGHPUT,
            value=5,
            agent_id="agent_1"
        )
        
        # Record recent metric
        collector.record_metric(
            MetricType.THROUGHPUT,
            value=10,
            agent_id="agent_1"
        )
        
        # Get recent metrics only
        recent = collector.get_metrics(
            MetricType.THROUGHPUT,
            agent_id="agent_1",
            time_window=timedelta(seconds=1)
        )
        
        assert len(recent) >= 1
    
    def test_calculate_statistics(self):
        """Test calculating statistics"""
        collector = MetricsCollector()
        
        values = [10, 20, 30, 40, 50]
        for value in values:
            collector.record_metric(
                MetricType.THROUGHPUT,
                value=value,
                agent_id="agent_1"
            )
        
        stats = collector.calculate_statistics(
            MetricType.THROUGHPUT,
            agent_id="agent_1"
        )
        
        assert stats["count"] == 5
        assert stats["min"] == 10
        assert stats["max"] == 50
        assert stats["mean"] == 30


class TestPerformanceAnalyzer:
    """Test performance analysis"""
    
    def test_get_agent_performance(self):
        """Test getting agent performance metrics"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        
        # Record metrics
        for i in range(50):
            collector.record_metric(
                MetricType.THROUGHPUT,
                value=10 + (i % 5),
                agent_id="agent_1"
            )
            collector.record_metric(
                MetricType.LATENCY,
                value=100 + (i % 50),
                agent_id="agent_1"
            )
            collector.record_metric(
                MetricType.ERROR_RATE,
                value=2 + (i % 3),
                agent_id="agent_1"
            )
        
        performance = analyzer.get_agent_performance("agent_1")
        
        assert performance.throughput > 0
        assert performance.latency_p50 > 0
        assert performance.latency_p95 > 0
        assert performance.error_rate >= 0
    
    def test_detect_bottlenecks(self):
        """Test detecting bottlenecks"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        
        # Record high latency
        for i in range(50):
            collector.record_metric(
                MetricType.LATENCY,
                value=6000,  # > 5 seconds
                workflow_id="workflow_1"
            )
        
        bottlenecks = analyzer.detect_bottlenecks("workflow_1")
        
        assert len(bottlenecks) > 0
        assert any("latency" in b.lower() for b in bottlenecks)


class TestHealthMonitor:
    """Test health monitoring"""
    
    def test_check_agent_health_healthy(self):
        """Test checking health of healthy agent"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        monitor = HealthMonitor(analyzer)
        
        # Record good metrics
        for i in range(50):
            collector.record_metric(
                MetricType.ERROR_RATE,
                value=1,
                agent_id="agent_1"
            )
            collector.record_metric(
                MetricType.RESOURCE_USAGE,
                value=50,
                agent_id="agent_1"
            )
        
        health = monitor.check_agent_health("agent_1")
        
        assert health.status == "healthy"
        assert len(health.issues) == 0
    
    def test_check_agent_health_degraded(self):
        """Test checking health of degraded agent"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        monitor = HealthMonitor(analyzer)
        
        # Record degraded metrics
        for i in range(50):
            collector.record_metric(
                MetricType.ERROR_RATE,
                value=7,
                agent_id="agent_1"
            )
            collector.record_metric(
                MetricType.RESOURCE_USAGE,
                value=85,
                agent_id="agent_1"
            )
        
        health = monitor.check_agent_health("agent_1")
        
        assert health.status == "degraded"
        assert len(health.issues) > 0
    
    def test_check_threshold_violations(self):
        """Test checking threshold violations"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        monitor = HealthMonitor(analyzer)
        
        # Record high error rate
        for i in range(50):
            collector.record_metric(
                MetricType.ERROR_RATE,
                value=10,
                agent_id="agent_1"
            )
        
        violations = monitor.check_threshold_violations(agent_id="agent_1")
        
        assert len(violations) > 0


class TestMetricsReporter:
    """Test metrics reporting"""
    
    def test_generate_agent_report(self):
        """Test generating agent report"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        monitor = HealthMonitor(analyzer)
        reporter = MetricsReporter(analyzer, monitor)
        
        # Record metrics
        for i in range(50):
            collector.record_metric(
                MetricType.THROUGHPUT,
                value=10,
                agent_id="agent_1"
            )
            collector.record_metric(
                MetricType.ERROR_RATE,
                value=2,
                agent_id="agent_1"
            )
        
        report = reporter.generate_agent_report("agent_1")
        
        assert report["agent_id"] == "agent_1"
        assert "health" in report
        assert "performance" in report
        assert report["health"]["status"] in ["healthy", "degraded", "unhealthy"]
    
    def test_generate_system_report(self):
        """Test generating system report"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        monitor = HealthMonitor(analyzer)
        reporter = MetricsReporter(analyzer, monitor)
        
        # Record metrics for multiple agents
        for agent_id in ["agent_1", "agent_2", "agent_3"]:
            for i in range(30):
                collector.record_metric(
                    MetricType.THROUGHPUT,
                    value=10,
                    agent_id=agent_id
                )
                collector.record_metric(
                    MetricType.ERROR_RATE,
                    value=2,
                    agent_id=agent_id
                )
        
        report = reporter.generate_system_report(["agent_1", "agent_2", "agent_3"])
        
        assert report["total_agents"] == 3
        assert len(report["agent_reports"]) == 3
        assert report["system_health"] in ["healthy", "degraded"]


class TestMetricsIntegration:
    """Integration tests for monitoring"""
    
    def test_complete_monitoring_workflow(self):
        """Test complete monitoring workflow"""
        collector = MetricsCollector()
        analyzer = PerformanceAnalyzer(collector)
        monitor = HealthMonitor(analyzer)
        reporter = MetricsReporter(analyzer, monitor)
        
        # Simulate agent activity
        for agent_id in ["agent_1", "agent_2"]:
            for i in range(100):
                collector.record_metric(
                    MetricType.THROUGHPUT,
                    value=10 + (i % 5),
                    agent_id=agent_id
                )
                collector.record_metric(
                    MetricType.LATENCY,
                    value=100 + (i % 50),
                    agent_id=agent_id
                )
                collector.record_metric(
                    MetricType.ERROR_RATE,
                    value=2 + (i % 3),
                    agent_id=agent_id
                )
        
        # Generate reports
        for agent_id in ["agent_1", "agent_2"]:
            health = monitor.check_agent_health(agent_id)
            assert health.status in ["healthy", "degraded", "unhealthy"]
            
            report = reporter.generate_agent_report(agent_id)
            assert "performance" in report
