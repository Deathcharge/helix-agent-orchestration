"""
Plugin System and Extension Framework

Provides a sophisticated plugin system for extending orchestration capabilities.

Features:
- Plugin registration and discovery
- Plugin lifecycle management
- Hook system
- Plugin configuration
- Plugin validation
"""

import importlib
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Types of plugins."""
    AGENT_CORE = "agent_core"
    COORDINATION = "coordination"
    MONITORING = "monitoring"
    OPTIMIZATION = "optimization"
    RESILIENCE = "resilience"
    CUSTOM = "custom"


class HookType(Enum):
    """Types of hooks."""
    BEFORE_AGENT_INIT = "before_agent_init"
    AFTER_AGENT_INIT = "after_agent_init"
    BEFORE_COORDINATION = "before_coordination"
    AFTER_COORDINATION = "after_coordination"
    BEFORE_TASK_EXECUTION = "before_task_execution"
    AFTER_TASK_EXECUTION = "after_task_execution"
    ON_ERROR = "on_error"
    ON_METRICS_COLLECTED = "on_metrics_collected"


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    author: str
    description: str
    plugin_type: PluginType
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "type": self.plugin_type.value,
            "dependencies": self.dependencies,
        }


class Plugin(ABC):
    """Base class for plugins."""
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata.
        
        Returns:
            PluginMetadata
        """
        pass
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize plugin.
        
        Args:
            config: Plugin configuration
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        pass
    
    async def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate plugin configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        return []


class HookHandler:
    """Manages hook handlers."""
    
    def __init__(self):
        """Initialize hook handler."""
        self.hooks: Dict[HookType, List[Callable]] = {
            hook_type: [] for hook_type in HookType
        }
        self.lock = None
    
    def register_hook(self, hook_type: HookType, handler: Callable) -> None:
        """Register a hook handler.
        
        Args:
            hook_type: Type of hook
            handler: Handler function
        """
        self.hooks[hook_type].append(handler)
        logger.info(f"Registered hook handler for {hook_type.value}")
    
    def unregister_hook(self, hook_type: HookType, handler: Callable) -> bool:
        """Unregister a hook handler.
        
        Args:
            hook_type: Type of hook
            handler: Handler function
            
        Returns:
            True if unregistered, False if not found
        """
        if handler in self.hooks[hook_type]:
            self.hooks[hook_type].remove(handler)
            return True
        return False
    
    async def trigger_hook(self, hook_type: HookType, **kwargs) -> List[Any]:
        """Trigger a hook.
        
        Args:
            hook_type: Type of hook
            **kwargs: Hook arguments
            
        Returns:
            List of results from handlers
        """
        results = []
        
        for handler in self.hooks[hook_type]:
            try:
                if inspect.iscoroutinefunction(handler):
                    result = await handler(**kwargs)
                else:
                    result = handler(**kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Error in hook handler: {e}")
        
        return results


class PluginRegistry:
    """Registry for managing plugins."""
    
    def __init__(self):
        """Initialize plugin registry."""
        self.plugins: Dict[str, Plugin] = {}
        self.metadata: Dict[str, PluginMetadata] = {}
        self.hooks = HookHandler()
        self.enabled_plugins: set = set()
    
    async def register_plugin(
        self,
        plugin: Plugin,
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Register a plugin.
        
        Args:
            plugin: Plugin instance
            config: Plugin configuration
            
        Returns:
            True if registered successfully
        """
        metadata = plugin.get_metadata()
        
        # Check dependencies
        for dep in metadata.dependencies:
            if dep not in self.plugins:
                logger.error(f"Dependency {dep} not found for plugin {metadata.name}")
                return False
        
        # Validate configuration
        config = config or {}
        errors = await plugin.validate_config(config)
        if errors:
            logger.error(f"Configuration errors for {metadata.name}: {errors}")
            return False
        
        # Initialize plugin
        try:
            await plugin.initialize(config)
        except Exception as e:
            logger.error(f"Failed to initialize plugin {metadata.name}: {e}")
            return False
        
        # Register
        self.plugins[metadata.name] = plugin
        self.metadata[metadata.name] = metadata
        self.enabled_plugins.add(metadata.name)
        
        logger.info(f"Registered plugin: {metadata.name} v{metadata.version}")
        return True
    
    async def unregister_plugin(self, name: str) -> bool:
        """Unregister a plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            True if unregistered
        """
        if name not in self.plugins:
            return False
        
        try:
            await self.plugins[name].shutdown()
        except Exception as e:
            logger.error(f"Error shutting down plugin {name}: {e}")
        
        del self.plugins[name]
        del self.metadata[name]
        self.enabled_plugins.discard(name)
        
        logger.info(f"Unregistered plugin: {name}")
        return True
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name.
        
        Args:
            name: Plugin name
            
        Returns:
            Plugin or None
        """
        return self.plugins.get(name)
    
    def get_plugins_by_type(self, plugin_type: PluginType) -> List[Plugin]:
        """Get plugins by type.
        
        Args:
            plugin_type: Plugin type
            
        Returns:
            List of plugins
        """
        return [
            plugin for name, plugin in self.plugins.items()
            if self.metadata[name].plugin_type == plugin_type
        ]
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins.
        
        Returns:
            List of plugin metadata
        """
        return [
            {
                **metadata.to_dict(),
                "enabled": name in self.enabled_plugins,
            }
            for name, metadata in self.metadata.items()
        ]
    
    def enable_plugin(self, name: str) -> bool:
        """Enable a plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            True if enabled
        """
        if name in self.plugins:
            self.enabled_plugins.add(name)
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """Disable a plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            True if disabled
        """
        if name in self.plugins:
            self.enabled_plugins.discard(name)
            return True
        return False
    
    async def shutdown_all(self) -> None:
        """Shutdown all plugins."""
        for name in list(self.plugins.keys()):
            await self.unregister_plugin(name)


class PluginLoader:
    """Loads plugins from modules."""
    
    @staticmethod
    def load_plugin_from_module(module_path: str, class_name: str) -> Optional[Type[Plugin]]:
        """Load plugin class from module.
        
        Args:
            module_path: Path to module (e.g., 'my_plugins.custom_agent')
            class_name: Name of plugin class
            
        Returns:
            Plugin class or None
        """
        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            
            if not issubclass(plugin_class, Plugin):
                logger.error(f"{class_name} is not a Plugin subclass")
                return None
            
            return plugin_class
        except Exception as e:
            logger.error(f"Failed to load plugin from {module_path}.{class_name}: {e}")
            return None
    
    @staticmethod
    def load_plugin_from_file(filepath: str, class_name: str) -> Optional[Type[Plugin]]:
        """Load plugin class from file.
        
        Args:
            filepath: Path to Python file
            class_name: Name of plugin class
            
        Returns:
            Plugin class or None
        """
        import sys
        import importlib.util
        
        try:
            spec = importlib.util.spec_from_file_location("plugin_module", filepath)
            module = importlib.util.module_from_spec(spec)
            sys.modules["plugin_module"] = module
            spec.loader.exec_module(module)
            
            plugin_class = getattr(module, class_name)
            
            if not issubclass(plugin_class, Plugin):
                logger.error(f"{class_name} is not a Plugin subclass")
                return None
            
            return plugin_class
        except Exception as e:
            logger.error(f"Failed to load plugin from {filepath}: {e}")
            return None


class PluginManager:
    """Main plugin manager."""
    
    def __init__(self):
        """Initialize plugin manager."""
        self.registry = PluginRegistry()
        self.loader = PluginLoader()
    
    async def load_and_register_plugin(
        self,
        module_path: str,
        class_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Load and register a plugin.
        
        Args:
            module_path: Module path
            class_name: Class name
            config: Plugin configuration
            
        Returns:
            True if successful
        """
        plugin_class = self.loader.load_plugin_from_module(module_path, class_name)
        if not plugin_class:
            return False
        
        plugin = plugin_class()
        return await self.registry.register_plugin(plugin, config)
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """Get system overview.
        
        Returns:
            Dictionary with overview
        """
        return {
            "total_plugins": len(self.registry.plugins),
            "enabled_plugins": len(self.registry.enabled_plugins),
            "plugins": self.registry.list_plugins(),
        }
