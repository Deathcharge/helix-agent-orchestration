"""
Distributed Tracing Module

Provides comprehensive distributed tracing capabilities for tracking
requests and operations across the orchestration system.

Features:
- Request tracing with trace IDs
- Span creation and tracking
- Context propagation
- Performance analysis
- Error tracking
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio
from collections import defaultdict


class SpanStatus(Enum):
    """Status of a span."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Span:
    """Represents a single span in a trace."""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    status: SpanStatus = SpanStatus.PENDING
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "tags": self.tags,
            "logs": self.logs,
            "error": self.error,
        }


@dataclass
class Trace:
    """Represents a complete trace."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    root_span_id: str = ""
    spans: Dict[str, Span] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    status: SpanStatus = SpanStatus.PENDING
    tags: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary."""
        return {
            "trace_id": self.trace_id,
            "root_span_id": self.root_span_id,
            "spans": [span.to_dict() for span in self.spans.values()],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "tags": self.tags,
        }


class TracingContext:
    """Thread-local context for tracing."""
    
    def __init__(self):
        """Initialize tracing context."""
        self.trace_id: Optional[str] = None
        self.current_span_id: Optional[str] = None
        self.span_stack: List[str] = []


class DistributedTracer:
    """Manages distributed tracing across the system."""
    
    def __init__(self, max_traces: int = 1000):
        """Initialize distributed tracer.
        
        Args:
            max_traces: Maximum number of traces to keep in memory
        """
        self.max_traces = max_traces
        self.traces: Dict[str, Trace] = {}
        self.active_spans: Dict[str, Span] = {}
        self.context = TracingContext()
        self.lock = asyncio.Lock()
    
    def start_trace(self, trace_id: Optional[str] = None) -> str:
        """Start a new trace.
        
        Args:
            trace_id: Optional trace ID (generated if not provided)
            
        Returns:
            Trace ID
        """
        trace_id = trace_id or str(uuid.uuid4())
        
        trace = Trace(trace_id=trace_id)
        self.traces[trace_id] = trace
        self.context.trace_id = trace_id
        
        # Limit number of traces in memory
        if len(self.traces) > self.max_traces:
            oldest_trace_id = min(
                self.traces.keys(),
                key=lambda tid: self.traces[tid].start_time
            )
            del self.traces[oldest_trace_id]
        
        return trace_id
    
    def start_span(
        self,
        operation_name: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new span.
        
        Args:
            operation_name: Name of operation
            trace_id: Trace ID (uses current context if not provided)
            parent_span_id: Parent span ID (uses current span if not provided)
            tags: Optional tags for span
            
        Returns:
            Span ID
        """
        trace_id = trace_id or self.context.trace_id or self.start_trace()
        parent_span_id = parent_span_id or self.context.current_span_id
        
        span = Span(
            trace_id=trace_id,
            operation_name=operation_name,
            parent_span_id=parent_span_id,
            status=SpanStatus.RUNNING,
            tags=tags or {},
        )
        
        self.active_spans[span.span_id] = span
        self.context.current_span_id = span.span_id
        self.context.span_stack.append(span.span_id)
        
        # Add span to trace
        if trace_id in self.traces:
            self.traces[trace_id].spans[span.span_id] = span
            if not self.traces[trace_id].root_span_id:
                self.traces[trace_id].root_span_id = span.span_id
        
        return span.span_id
    
    def end_span(
        self,
        span_id: str,
        status: SpanStatus = SpanStatus.SUCCESS,
        error: Optional[str] = None,
    ) -> None:
        """End a span.
        
        Args:
            span_id: Span ID
            status: Final status of span
            error: Optional error message
        """
        if span_id not in self.active_spans:
            return
        
        span = self.active_spans[span_id]
        span.end_time = datetime.utcnow()
        span.duration_ms = (span.end_time - span.start_time).total_seconds() * 1000
        span.status = status
        span.error = error
        
        # Update trace
        if span.trace_id in self.traces:
            trace = self.traces[span.trace_id]
            trace.spans[span_id] = span
        
        # Pop from stack
        if self.context.span_stack and self.context.span_stack[-1] == span_id:
            self.context.span_stack.pop()
            self.context.current_span_id = self.context.span_stack[-1] if self.context.span_stack else None
        
        del self.active_spans[span_id]
    
    def add_span_tag(self, span_id: str, key: str, value: Any) -> None:
        """Add a tag to a span.
        
        Args:
            span_id: Span ID
            key: Tag key
            value: Tag value
        """
        if span_id in self.active_spans:
            self.active_spans[span_id].tags[key] = value
    
    def add_span_log(self, span_id: str, message: str, **fields) -> None:
        """Add a log entry to a span.
        
        Args:
            span_id: Span ID
            message: Log message
            **fields: Additional fields
        """
        if span_id in self.active_spans:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "message": message,
                **fields,
            }
            self.active_spans[span_id].logs.append(log_entry)
    
    def end_trace(self, trace_id: str) -> Optional[Trace]:
        """End a trace.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Completed trace or None
        """
        if trace_id not in self.traces:
            return None
        
        trace = self.traces[trace_id]
        trace.end_time = datetime.utcnow()
        trace.duration_ms = (trace.end_time - trace.start_time).total_seconds() * 1000
        
        # Determine trace status
        if any(span.status == SpanStatus.ERROR for span in trace.spans.values()):
            trace.status = SpanStatus.ERROR
        else:
            trace.status = SpanStatus.SUCCESS
        
        return trace
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Get a trace by ID.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Trace or None
        """
        return self.traces.get(trace_id)
    
    def get_span(self, span_id: str) -> Optional[Span]:
        """Get a span by ID.
        
        Args:
            span_id: Span ID
            
        Returns:
            Span or None
        """
        return self.active_spans.get(span_id)
    
    def get_trace_tree(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get trace as a tree structure.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Tree structure or None
        """
        trace = self.get_trace(trace_id)
        if not trace:
            return None
        
        def build_tree(span_id: Optional[str]) -> Dict[str, Any]:
            if not span_id or span_id not in trace.spans:
                return {}
            
            span = trace.spans[span_id]
            children = [
                build_tree(child_id)
                for child_id, child_span in trace.spans.items()
                if child_span.parent_span_id == span_id
            ]
            
            return {
                "span": span.to_dict(),
                "children": [c for c in children if c],
            }
        
        return build_tree(trace.root_span_id)
    
    def get_recent_traces(self, limit: int = 100) -> List[Trace]:
        """Get recent traces.
        
        Args:
            limit: Maximum number of traces
            
        Returns:
            List of traces
        """
        traces = sorted(
            self.traces.values(),
            key=lambda t: t.start_time,
            reverse=True,
        )
        return traces[:limit]
    
    def get_slow_traces(self, threshold_ms: float = 1000, limit: int = 100) -> List[Trace]:
        """Get traces that took longer than threshold.
        
        Args:
            threshold_ms: Threshold in milliseconds
            limit: Maximum number of traces
            
        Returns:
            List of slow traces
        """
        slow_traces = [
            t for t in self.traces.values()
            if t.duration_ms >= threshold_ms
        ]
        slow_traces.sort(key=lambda t: t.duration_ms, reverse=True)
        return slow_traces[:limit]
    
    def get_error_traces(self, limit: int = 100) -> List[Trace]:
        """Get traces with errors.
        
        Args:
            limit: Maximum number of traces
            
        Returns:
            List of error traces
        """
        error_traces = [
            t for t in self.traces.values()
            if t.status == SpanStatus.ERROR
        ]
        error_traces.sort(key=lambda t: t.start_time, reverse=True)
        return error_traces[:limit]


class SpanContextManager:
    """Context manager for spans."""
    
    def __init__(self, tracer: DistributedTracer, operation_name: str):
        """Initialize span context manager.
        
        Args:
            tracer: DistributedTracer instance
            operation_name: Name of operation
        """
        self.tracer = tracer
        self.operation_name = operation_name
        self.span_id: Optional[str] = None
    
    async def __aenter__(self) -> str:
        """Enter context."""
        self.span_id = self.tracer.start_span(self.operation_name)
        return self.span_id
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context."""
        if exc_type:
            self.tracer.end_span(
                self.span_id,
                status=SpanStatus.ERROR,
                error=str(exc_val),
            )
        else:
            self.tracer.end_span(self.span_id)
