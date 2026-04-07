"""
Advanced Configuration System

Provides sophisticated configuration management with validation,
defaults, environment variable support, and dynamic updates.

Features:
- Configuration validation
- Environment variable support
- Default values
- Configuration profiles
- Dynamic updates
- Configuration export/import
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Type, TypeVar
from enum import Enum
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ConfigProfile(Enum):
    """Configuration profiles."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class OrchestratorConfig:
    """Orchestrator configuration."""
    max_agents: int = 18
    coordination_timeout: int = 30
    handshake_timeout: int = 5
    enable_ethics: bool = True
    enable_resonance: bool = True
    enable_autonomy_scoring: bool = True
    enable_metrics_caching: bool = True
    metrics_cache_ttl: int = 60
    enable_compression: bool = False
    log_level: str = "INFO"
    consensus_threshold: float = 0.8


@dataclass
class MonitoringConfig:
    """Monitoring configuration."""
    enable_monitoring: bool = True
    metrics_collection_interval: int = 5
    max_metrics_history: int = 1000
    enable_health_checks: bool = True
    health_check_interval: int = 30
    enable_tracing: bool = True
    max_traces: int = 1000
    enable_alerts: bool = True
    alert_check_interval: int = 10


@dataclass
class CachingConfig:
    """Caching configuration."""
    enable_caching: bool = True
    cache_ttl: int = 300
    max_cache_size: int = 10000
    cache_eviction_policy: str = "lru"  # lru, lfu, fifo
    enable_compression: bool = False
    compression_level: int = 6


@dataclass
class ResilienceConfig:
    """Resilience configuration."""
    enable_retry: bool = True
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60
    enable_rate_limiting: bool = True
    rate_limit_requests: int = 1000
    rate_limit_window: int = 60


@dataclass
class AdvancedConfig:
    """Advanced configuration combining all modules."""
    profile: ConfigProfile = ConfigProfile.DEVELOPMENT
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    caching: CachingConfig = field(default_factory=CachingConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
    custom_settings: Dict[str, Any] = field(default_factory=dict)


class ConfigValidator:
    """Validates configuration values."""
    
    @staticmethod
    def validate_orchestrator_config(config: OrchestratorConfig) -> List[str]:
        """Validate orchestrator configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if config.max_agents < 1 or config.max_agents > 100:
            errors.append("max_agents must be between 1 and 100")
        
        if config.coordination_timeout < 1 or config.coordination_timeout > 300:
            errors.append("coordination_timeout must be between 1 and 300 seconds")
        
        if config.handshake_timeout < 1 or config.handshake_timeout > 60:
            errors.append("handshake_timeout must be between 1 and 60 seconds")
        
        if not 0 <= config.consensus_threshold <= 1:
            errors.append("consensus_threshold must be between 0 and 1")
        
        return errors
    
    @staticmethod
    def validate_monitoring_config(config: MonitoringConfig) -> List[str]:
        """Validate monitoring configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if config.metrics_collection_interval < 1:
            errors.append("metrics_collection_interval must be at least 1 second")
        
        if config.max_metrics_history < 100:
            errors.append("max_metrics_history must be at least 100")
        
        if config.health_check_interval < 5:
            errors.append("health_check_interval must be at least 5 seconds")
        
        return errors
    
    @staticmethod
    def validate_caching_config(config: CachingConfig) -> List[str]:
        """Validate caching configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if config.cache_ttl < 0:
            errors.append("cache_ttl must be non-negative")
        
        if config.max_cache_size < 100:
            errors.append("max_cache_size must be at least 100")
        
        if config.cache_eviction_policy not in ["lru", "lfu", "fifo"]:
            errors.append("cache_eviction_policy must be lru, lfu, or fifo")
        
        if not 1 <= config.compression_level <= 9:
            errors.append("compression_level must be between 1 and 9")
        
        return errors
    
    @staticmethod
    def validate_resilience_config(config: ResilienceConfig) -> List[str]:
        """Validate resilience configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if config.max_retries < 0 or config.max_retries > 10:
            errors.append("max_retries must be between 0 and 10")
        
        if config.retry_backoff_base < 1:
            errors.append("retry_backoff_base must be at least 1")
        
        if config.circuit_breaker_threshold < 1:
            errors.append("circuit_breaker_threshold must be at least 1")
        
        if config.rate_limit_requests < 1:
            errors.append("rate_limit_requests must be at least 1")
        
        return errors


class ConfigurationManager:
    """Manages configuration with validation and environment support."""
    
    def __init__(self, profile: ConfigProfile = ConfigProfile.DEVELOPMENT):
        """Initialize configuration manager.
        
        Args:
            profile: Configuration profile to use
        """
        self.profile = profile
        self.config = AdvancedConfig(profile=profile)
        self.load_from_environment()
    
    def load_from_environment(self) -> None:
        """Load configuration from environment variables."""
        # Orchestrator settings
        if "HELIX_MAX_AGENTS" in os.environ:
            self.config.orchestrator.max_agents = int(os.environ["HELIX_MAX_AGENTS"])
        
        if "HELIX_COORDINATION_TIMEOUT" in os.environ:
            self.config.orchestrator.coordination_timeout = int(os.environ["HELIX_COORDINATION_TIMEOUT"])
        
        if "HELIX_LOG_LEVEL" in os.environ:
            self.config.orchestrator.log_level = os.environ["HELIX_LOG_LEVEL"]
        
        # Monitoring settings
        if "HELIX_ENABLE_MONITORING" in os.environ:
            self.config.monitoring.enable_monitoring = os.environ["HELIX_ENABLE_MONITORING"].lower() == "true"
        
        # Caching settings
        if "HELIX_ENABLE_CACHING" in os.environ:
            self.config.caching.enable_caching = os.environ["HELIX_ENABLE_CACHING"].lower() == "true"
        
        if "HELIX_CACHE_TTL" in os.environ:
            self.config.caching.cache_ttl = int(os.environ["HELIX_CACHE_TTL"])
    
    def validate(self) -> bool:
        """Validate current configuration.
        
        Returns:
            True if valid, False otherwise
        """
        errors = []
        
        errors.extend(ConfigValidator.validate_orchestrator_config(self.config.orchestrator))
        errors.extend(ConfigValidator.validate_monitoring_config(self.config.monitoring))
        errors.extend(ConfigValidator.validate_caching_config(self.config.caching))
        errors.extend(ConfigValidator.validate_resilience_config(self.config.resilience))
        
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            return False
        
        return True
    
    def update_orchestrator_config(self, **kwargs) -> None:
        """Update orchestrator configuration.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        for key, value in kwargs.items():
            if hasattr(self.config.orchestrator, key):
                setattr(self.config.orchestrator, key, value)
    
    def update_monitoring_config(self, **kwargs) -> None:
        """Update monitoring configuration.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        for key, value in kwargs.items():
            if hasattr(self.config.monitoring, key):
                setattr(self.config.monitoring, key, value)
    
    def update_caching_config(self, **kwargs) -> None:
        """Update caching configuration.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        for key, value in kwargs.items():
            if hasattr(self.config.caching, key):
                setattr(self.config.caching, key, value)
    
    def update_resilience_config(self, **kwargs) -> None:
        """Update resilience configuration.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        for key, value in kwargs.items():
            if hasattr(self.config.resilience, key):
                setattr(self.config.resilience, key, value)
    
    def export_to_dict(self) -> Dict[str, Any]:
        """Export configuration to dictionary.
        
        Returns:
            Configuration as dictionary
        """
        return asdict(self.config)
    
    def export_to_json(self, filepath: str) -> None:
        """Export configuration to JSON file.
        
        Args:
            filepath: Path to save JSON file
        """
        with open(filepath, 'w') as f:
            json.dump(self.export_to_dict(), f, indent=2)
    
    def import_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """Import configuration from dictionary.
        
        Args:
            config_dict: Configuration dictionary
        """
        if "orchestrator" in config_dict:
            self.config.orchestrator = OrchestratorConfig(**config_dict["orchestrator"])
        if "monitoring" in config_dict:
            self.config.monitoring = MonitoringConfig(**config_dict["monitoring"])
        if "caching" in config_dict:
            self.config.caching = CachingConfig(**config_dict["caching"])
        if "resilience" in config_dict:
            self.config.resilience = ResilienceConfig(**config_dict["resilience"])
    
    def import_from_json(self, filepath: str) -> None:
        """Import configuration from JSON file.
        
        Args:
            filepath: Path to JSON file
        """
        with open(filepath, 'r') as f:
            config_dict = json.load(f)
        self.import_from_dict(config_dict)
    
    def get_profile_defaults(self, profile: ConfigProfile) -> AdvancedConfig:
        """Get default configuration for a profile.
        
        Args:
            profile: Configuration profile
            
        Returns:
            Default configuration
        """
        config = AdvancedConfig(profile=profile)
        
        if profile == ConfigProfile.DEVELOPMENT:
            config.orchestrator.log_level = "DEBUG"
            config.monitoring.enable_monitoring = True
            config.caching.enable_caching = False
        
        elif profile == ConfigProfile.STAGING:
            config.orchestrator.log_level = "INFO"
            config.monitoring.enable_monitoring = True
            config.caching.enable_caching = True
            config.caching.cache_ttl = 300
        
        elif profile == ConfigProfile.PRODUCTION:
            config.orchestrator.log_level = "WARNING"
            config.monitoring.enable_monitoring = True
            config.caching.enable_caching = True
            config.caching.cache_ttl = 600
            config.resilience.enable_retry = True
            config.resilience.enable_circuit_breaker = True
        
        return config
