"""
Advanced Logging and Debugging Module

Provides sophisticated logging, debugging, and diagnostic capabilities.

Features:
- Structured logging
- Log levels and filtering
- Performance profiling
- Debug mode
- Log aggregation
"""

import logging
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
import asyncio


class LogLevel(Enum):
    """Log levels."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


@dataclass
class LogEntry:
    """Represents a log entry."""
    timestamp: str
    level: str
    logger_name: str
    message: str
    context: Dict[str, Any]
    exception: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON."""
        return json.dumps(self.to_dict())


class StructuredLogger:
    """Provides structured logging capabilities."""
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        """Initialize structured logger.
        
        Args:
            name: Logger name
            level: Log level
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level.value)
        self.entries: List[LogEntry] = []
        self.max_entries = 10000
    
    def _create_entry(
        self,
        level: str,
        message: str,
        context: Dict[str, Any],
        exception: Optional[str] = None,
    ) -> LogEntry:
        """Create log entry.
        
        Args:
            level: Log level
            message: Log message
            context: Context dictionary
            exception: Optional exception info
            
        Returns:
            LogEntry
        """
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=level,
            logger_name=self.logger.name,
            message=message,
            context=context,
            exception=exception,
        )
        
        # Store entry
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)
        
        return entry
    
    def debug(self, message: str, **context) -> None:
        """Log debug message.
        
        Args:
            message: Log message
            **context: Context data
        """
        entry = self._create_entry("DEBUG", message, context)
        self.logger.debug(entry.to_json())
    
    def info(self, message: str, **context) -> None:
        """Log info message.
        
        Args:
            message: Log message
            **context: Context data
        """
        entry = self._create_entry("INFO", message, context)
        self.logger.info(entry.to_json())
    
    def warning(self, message: str, **context) -> None:
        """Log warning message.
        
        Args:
            message: Log message
            **context: Context data
        """
        entry = self._create_entry("WARNING", message, context)
        self.logger.warning(entry.to_json())
    
    def error(self, message: str, exception: Optional[Exception] = None, **context) -> None:
        """Log error message.
        
        Args:
            message: Log message
            exception: Optional exception
            **context: Context data
        """
        exc_str = str(exception) if exception else None
        entry = self._create_entry("ERROR", message, context, exc_str)
        self.logger.error(entry.to_json(), exc_info=exception)
    
    def critical(self, message: str, exception: Optional[Exception] = None, **context) -> None:
        """Log critical message.
        
        Args:
            message: Log message
            exception: Optional exception
            **context: Context data
        """
        exc_str = str(exception) if exception else None
        entry = self._create_entry("CRITICAL", message, context, exc_str)
        self.logger.critical(entry.to_json(), exc_info=exception)
    
    def get_entries(self, level: Optional[str] = None, limit: int = 100) -> List[LogEntry]:
        """Get log entries.
        
        Args:
            level: Optional log level filter
            limit: Maximum entries to return
            
        Returns:
            List of log entries
        """
        entries = self.entries
        if level:
            entries = [e for e in entries if e.level == level]
        return entries[-limit:]
    
    def clear_entries(self) -> int:
        """Clear all entries.
        
        Returns:
            Number of entries cleared
        """
        count = len(self.entries)
        self.entries.clear()
        return count


class PerformanceProfiler:
    """Profiles performance of operations."""
    
    def __init__(self):
        """Initialize performance profiler."""
        self.profiles: Dict[str, List[float]] = {}
        self.lock = asyncio.Lock()
    
    async def profile(self, operation_name: str, func, *args, **kwargs) -> Any:
        """Profile function execution.
        
        Args:
            operation_name: Name of operation
            func: Function to profile
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            
            async with self.lock:
                if operation_name not in self.profiles:
                    self.profiles[operation_name] = []
                self.profiles[operation_name].append(duration)
    
    async def get_profile_stats(self, operation_name: str) -> Dict[str, float]:
        """Get profiling statistics.
        
        Args:
            operation_name: Name of operation
            
        Returns:
            Dictionary with statistics
        """
        async with self.lock:
            durations = self.profiles.get(operation_name, [])
        
        if not durations:
            return {}
        
        import statistics
        return {
            "count": len(durations),
            "total": sum(durations),
            "min": min(durations),
            "max": max(durations),
            "mean": statistics.mean(durations),
            "median": statistics.median(durations),
        }
    
    async def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Get all profiling statistics.
        
        Returns:
            Dictionary with all statistics
        """
        stats = {}
        for operation_name in list(self.profiles.keys()):
            stats[operation_name] = await self.get_profile_stats(operation_name)
        return stats


class DebugMode:
    """Manages debug mode for the system."""
    
    def __init__(self):
        """Initialize debug mode."""
        self.enabled = False
        self.verbose = False
        self.breakpoints: Dict[str, bool] = {}
        self.watches: Dict[str, Any] = {}
    
    def enable(self, verbose: bool = False) -> None:
        """Enable debug mode.
        
        Args:
            verbose: Enable verbose output
        """
        self.enabled = True
        self.verbose = verbose
    
    def disable(self) -> None:
        """Disable debug mode."""
        self.enabled = False
        self.verbose = False
    
    def set_breakpoint(self, name: str) -> None:
        """Set a breakpoint.
        
        Args:
            name: Breakpoint name
        """
        self.breakpoints[name] = True
    
    def clear_breakpoint(self, name: str) -> None:
        """Clear a breakpoint.
        
        Args:
            name: Breakpoint name
        """
        if name in self.breakpoints:
            del self.breakpoints[name]
    
    def check_breakpoint(self, name: str) -> bool:
        """Check if breakpoint is set.
        
        Args:
            name: Breakpoint name
            
        Returns:
            True if breakpoint is set
        """
        return self.breakpoints.get(name, False)
    
    def watch(self, name: str, value: Any) -> None:
        """Watch a value.
        
        Args:
            name: Watch name
            value: Value to watch
        """
        self.watches[name] = value
    
    def get_watch(self, name: str) -> Optional[Any]:
        """Get watched value.
        
        Args:
            name: Watch name
            
        Returns:
            Watched value or None
        """
        return self.watches.get(name)


class DiagnosticCollector:
    """Collects diagnostic information."""
    
    def __init__(self):
        """Initialize diagnostic collector."""
        self.logger = StructuredLogger("diagnostics")
        self.profiler = PerformanceProfiler()
        self.debug_mode = DebugMode()
    
    async def collect_diagnostics(self) -> Dict[str, Any]:
        """Collect all diagnostic information.
        
        Returns:
            Dictionary with diagnostic data
        """
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "debug_enabled": self.debug_mode.enabled,
            "recent_logs": [e.to_dict() for e in self.logger.get_entries(limit=50)],
            "performance_stats": await self.profiler.get_all_stats(),
            "watches": self.debug_mode.watches,
        }
    
    async def export_diagnostics(self, filepath: str) -> None:
        """Export diagnostics to file.
        
        Args:
            filepath: Path to save diagnostics
        """
        diagnostics = await self.collect_diagnostics()
        with open(filepath, 'w') as f:
            json.dump(diagnostics, f, indent=2)
