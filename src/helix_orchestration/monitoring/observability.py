"""
Advanced Monitoring and Observability Module

Provides comprehensive monitoring, observability, and real-time insights into
orchestration system performance and health.

Features:
- Real-time metrics collection
- Performance monitoring
- Health checks and diagnostics
- Event tracking and logging
- Anomaly detection
- Alert management
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from collections import defaultdict, deque
import statistics
import logging

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics that can be collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class HealthStatus(Enum):
    """Health status indicators."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class Metric:
    """Represents a single metric data point."""
    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metric to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class HealthCheck:
    """Represents a health check result."""
    name: str
    status: HealthStatus
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert health check to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


@dataclass
class Alert:
    """Represents an alert triggered by monitoring."""
    name: str
    severity: str  # "info", "warning", "error", "critical"
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    current_value: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "name": self.name,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "current_value": self.current_value,
        }


class MetricsCollector:
    """Collects and aggregates metrics."""
    
    def __init__(self, max_history: int = 1000):
        """Initialize metrics collector.
        
        Args:
            max_history: Maximum number of metric points to keep in memory
        """
        self.max_history = max_history
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.lock = asyncio.Lock()
    
    async def record_metric(self, metric: Metric) -> None:
        """Record a metric.
        
        Args:
            metric: Metric to record
        """
        async with self.lock:
            self.metrics[metric.name].append(metric)
    
    async def get_metric_history(
        self,
        metric_name: str,
        limit: Optional[int] = None,
    ) -> List[Metric]:
        """Get metric history.
        
        Args:
            metric_name: Name of metric
            limit: Maximum number of records to return
            
        Returns:
            List of metrics
        """
        async with self.lock:
            metrics = list(self.metrics.get(metric_name, []))
            if limit:
                metrics = metrics[-limit:]
            return metrics
    
    async def get_metric_stats(self, metric_name: str) -> Dict[str, float]:
        """Get statistics for a metric.
        
        Args:
            metric_name: Name of metric
            
        Returns:
            Dictionary with statistics
        """
        async with self.lock:
            metrics = list(self.metrics.get(metric_name, []))
        
        if not metrics:
            return {}
        
        values = [m.value for m in metrics]
        
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "sum": sum(values),
        }
    
    async def clear_old_metrics(self, older_than: timedelta) -> int:
        """Clear metrics older than specified time.
        
        Args:
            older_than: Timedelta for cutoff
            
        Returns:
            Number of metrics cleared
        """
        cutoff = datetime.utcnow() - older_than
        cleared = 0
        
        async with self.lock:
            for metric_name in self.metrics:
                while self.metrics[metric_name]:
                    if self.metrics[metric_name][0].timestamp < cutoff:
                        self.metrics[metric_name].popleft()
                        cleared += 1
                    else:
                        break
        
        return cleared


class HealthChecker:
    """Performs health checks on system components."""
    
    def __init__(self):
        """Initialize health checker."""
        self.checks: Dict[str, Callable] = {}
        self.results: Dict[str, HealthCheck] = {}
        self.lock = asyncio.Lock()
    
    def register_check(
        self,
        name: str,
        check_func: Callable[[], Any],
    ) -> None:
        """Register a health check.
        
        Args:
            name: Name of health check
            check_func: Async function that returns health status
        """
        self.checks[name] = check_func
    
    async def run_check(self, name: str) -> Optional[HealthCheck]:
        """Run a specific health check.
        
        Args:
            name: Name of health check
            
        Returns:
            HealthCheck result or None if check not found
        """
        if name not in self.checks:
            return None
        
        try:
            result = await self.checks[name]()
            
            if isinstance(result, HealthCheck):
                health_check = result
            else:
                health_check = HealthCheck(
                    name=name,
                    status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                    message="Check passed" if result else "Check failed",
                )
            
            async with self.lock:
                self.results[name] = health_check
            
            return health_check
        except Exception as e:
            health_check = HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
                details={"error": str(e)},
            )
            
            async with self.lock:
                self.results[name] = health_check
            
            return health_check
    
    async def run_all_checks(self) -> Dict[str, HealthCheck]:
        """Run all registered health checks.
        
        Returns:
            Dictionary of check results
        """
        results = {}
        
        for check_name in self.checks:
            result = await self.run_check(check_name)
            if result:
                results[check_name] = result
        
        return results
    
    async def get_overall_status(self) -> HealthStatus:
        """Get overall system health status.
        
        Returns:
            Overall health status
        """
        async with self.lock:
            if not self.results:
                return HealthStatus.UNKNOWN
            
            statuses = [check.status for check in self.results.values()]
            
            if HealthStatus.UNHEALTHY in statuses:
                return HealthStatus.UNHEALTHY
            elif HealthStatus.DEGRADED in statuses:
                return HealthStatus.DEGRADED
            else:
                return HealthStatus.HEALTHY


class AlertManager:
    """Manages alerts and alert thresholds."""
    
    def __init__(self, max_alerts: int = 1000):
        """Initialize alert manager.
        
        Args:
            max_alerts: Maximum number of alerts to keep in memory
        """
        self.max_alerts = max_alerts
        self.alerts: deque = deque(maxlen=max_alerts)
        self.thresholds: Dict[str, Dict[str, float]] = {}
        self.alert_handlers: List[Callable] = []
        self.lock = asyncio.Lock()
    
    def set_threshold(
        self,
        metric_name: str,
        threshold_type: str,  # "warning", "error", "critical"
        value: float,
    ) -> None:
        """Set alert threshold for a metric.
        
        Args:
            metric_name: Name of metric
            threshold_type: Type of threshold
            value: Threshold value
        """
        if metric_name not in self.thresholds:
            self.thresholds[metric_name] = {}
        
        self.thresholds[metric_name][threshold_type] = value
    
    def register_alert_handler(self, handler: Callable) -> None:
        """Register a handler for alerts.
        
        Args:
            handler: Async function to call when alert is triggered
        """
        self.alert_handlers.append(handler)
    
    async def check_metric(self, metric: Metric) -> Optional[Alert]:
        """Check if metric triggers any alerts.
        
        Args:
            metric: Metric to check
            
        Returns:
            Alert if threshold exceeded, None otherwise
        """
        if metric.name not in self.thresholds:
            return None
        
        thresholds = self.thresholds[metric.name]
        alert = None
        
        for threshold_type in ["critical", "error", "warning"]:
            if threshold_type in thresholds:
                if metric.value > thresholds[threshold_type]:
                    alert = Alert(
                        name=f"{metric.name}_{threshold_type}",
                        severity=threshold_type,
                        message=f"Metric {metric.name} exceeded {threshold_type} threshold",
                        metric_name=metric.name,
                        threshold=thresholds[threshold_type],
                        current_value=metric.value,
                    )
                    break
        
        if alert:
            async with self.lock:
                self.alerts.append(alert)
            
            # Call alert handlers
            for handler in self.alert_handlers:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"Error in alert handler: {e}")
        
        return alert
    
    async def get_recent_alerts(self, limit: int = 100) -> List[Alert]:
        """Get recent alerts.
        
        Args:
            limit: Maximum number of alerts to return
            
        Returns:
            List of recent alerts
        """
        async with self.lock:
            alerts = list(self.alerts)
            return alerts[-limit:]
    
    async def clear_alerts(self) -> int:
        """Clear all alerts.
        
        Returns:
            Number of alerts cleared
        """
        async with self.lock:
            count = len(self.alerts)
            self.alerts.clear()
            return count


class PerformanceTracker:
    """Tracks performance metrics for operations."""
    
    def __init__(self):
        """Initialize performance tracker."""
        self.timers: Dict[str, List[float]] = defaultdict(list)
        self.lock = asyncio.Lock()
    
    async def record_duration(self, operation: str, duration: float) -> None:
        """Record operation duration.
        
        Args:
            operation: Name of operation
            duration: Duration in seconds
        """
        async with self.lock:
            self.timers[operation].append(duration)
    
    async def get_performance_stats(self, operation: str) -> Dict[str, float]:
        """Get performance statistics for an operation.
        
        Args:
            operation: Name of operation
            
        Returns:
            Dictionary with performance statistics
        """
        async with self.lock:
            durations = self.timers.get(operation, [])
        
        if not durations:
            return {}
        
        return {
            "count": len(durations),
            "min": min(durations),
            "max": max(durations),
            "mean": statistics.mean(durations),
            "median": statistics.median(durations),
            "p95": sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0],
            "p99": sorted(durations)[int(len(durations) * 0.99)] if len(durations) > 1 else durations[0],
            "total": sum(durations),
        }


class ObservabilityManager:
    """Main observability manager coordinating all monitoring."""
    
    def __init__(self):
        """Initialize observability manager."""
        self.metrics_collector = MetricsCollector()
        self.health_checker = HealthChecker()
        self.alert_manager = AlertManager()
        self.performance_tracker = PerformanceTracker()
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """Get comprehensive system overview.
        
        Returns:
            Dictionary with system overview
        """
        health_results = await self.health_checker.run_all_checks()
        overall_status = await self.health_checker.get_overall_status()
        recent_alerts = await self.alert_manager.get_recent_alerts(limit=10)
        
        return {
            "overall_status": overall_status.value,
            "health_checks": {
                name: check.to_dict()
                for name, check in health_results.items()
            },
            "recent_alerts": [alert.to_dict() for alert in recent_alerts],
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report.
        
        Returns:
            Dictionary with performance data
        """
        operations = [
            "agent_registration",
            "task_execution",
            "coordination",
            "metrics_collection",
        ]
        
        report = {}
        for operation in operations:
            stats = await self.performance_tracker.get_performance_stats(operation)
            if stats:
                report[operation] = stats
        
        return report
