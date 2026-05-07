#!/usr/bin/env python3
"""
Configuration management for QRL client.
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class ClientConfig:
    """Client configuration settings."""

    # Capture settings — 0.05s = 20 FPS, fast enough to catch a 10 FPS QR feed
    # with at least one frame per displayed code.
    # `monitor` is the 1-based mss index (1 = primary). 0 is accepted as a
    # legacy alias for primary.
    monitor: int = 1
    interval: float = 0.05
    timeout: int = 300
    region: Optional[Tuple[int, int, int, int]] = None

    # Processing settings
    progress_interval: float = 5.0
    save_progress: bool = False
    max_missing_chunks: int = 10
    retry_attempts: int = 3

    # Detection settings
    qr_detection_threshold: float = 0.3
    image_preprocessing: bool = True
    enhance_contrast: bool = True
    noise_reduction: bool = True

    # Output settings
    # `output_dir` is where decoded files land. Filename is read from the
    # stream manifest, so the user usually doesn't need to pick one upfront.
    # Empty string means "auto" — resolved to ~/Downloads/qrl_received at runtime.
    output_dir: str = ""
    output_buffer_size: int = 1024 * 1024  # 1MB
    temp_directory: Optional[str] = None
    cleanup_temp_files: bool = True

    # GUI settings
    window_width: int = 900
    window_height: int = 700
    show_preview: bool = True
    preview_size: Tuple[int, int] = (400, 300)

    # Advanced settings
    max_decode_attempts: int = 5
    frame_buffer_size: int = 50
    log_level: str = "INFO"

    def resolve_output_dir(self) -> str:
        """Returns the configured output_dir, or a sensible default."""
        if self.output_dir:
            return self.output_dir
        return str(Path.home() / "Downloads" / "qrl_received")

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ClientConfig':
        """Create config from dictionary, filtering unknown keys."""
        valid_keys = {field.name for field in cls.__dataclass_fields__.values()}
        filtered_dict = {k: v for k, v in config_dict.items() if k in valid_keys}

        # Handle tuple conversion for region and preview_size
        if 'region' in filtered_dict and filtered_dict['region'] is not None:
            if isinstance(filtered_dict['region'], list):
                filtered_dict['region'] = tuple(filtered_dict['region'])

        if 'preview_size' in filtered_dict:
            if isinstance(filtered_dict['preview_size'], list):
                filtered_dict['preview_size'] = tuple(filtered_dict['preview_size'])

        return cls(**filtered_dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        data = asdict(self)

        # Convert tuples to lists for JSON serialization
        if data['region'] is not None:
            data['region'] = list(data['region'])
        data['preview_size'] = list(data['preview_size'])

        return data

    def validate(self) -> bool:
        """Validate configuration values."""
        errors = []

        if self.monitor < 0:
            errors.append("monitor index must be non-negative (0 = primary, 1+ = mss index)")

        if self.interval <= 0 or self.interval > 60:
            errors.append("interval must be between 0 and 60 seconds")

        if self.timeout <= 0:
            errors.append("timeout must be positive")

        if self.region is not None:
            if len(self.region) != 4:
                errors.append("region must be a 4-tuple (x, y, width, height)")
            else:
                x, y, w, h = self.region
                # x and y can be negative on Windows when secondary monitors
                # extend to the left of / above the primary monitor.
                if w <= 0 or h <= 0:
                    errors.append("region width and height must be positive")

        if self.progress_interval <= 0:
            errors.append("progress_interval must be positive")

        if self.max_missing_chunks < 0:
            errors.append("max_missing_chunks must be non-negative")

        if self.retry_attempts < 0:
            errors.append("retry_attempts must be non-negative")

        if not 0 <= self.qr_detection_threshold <= 1:
            errors.append("qr_detection_threshold must be between 0 and 1")

        if self.output_buffer_size <= 0:
            errors.append("output_buffer_size must be positive")

        if self.window_width <= 0 or self.window_height <= 0:
            errors.append("window dimensions must be positive")

        if len(self.preview_size) != 2 or any(val <= 0 for val in self.preview_size):
            errors.append("preview_size must be a 2-tuple of positive integers")

        if self.max_decode_attempts <= 0:
            errors.append("max_decode_attempts must be positive")

        if self.frame_buffer_size <= 0:
            errors.append("frame_buffer_size must be positive")

        if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            errors.append("log_level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

        return True


class ClientConfigManager:
    """Manages loading and saving client configuration files."""

    DEFAULT_CONFIG_PATHS = [
        "qrl_client.yaml",
        "qrl_client.yml",
        "qrl_client.json",
        "config/qrl_client.yaml",
        "config/qrl_client.yml",
        "config/qrl_client.json",
        os.path.expanduser("~/.qrl/client_config.yaml"),
        os.path.expanduser("~/.qrl/client_config.yml"),
        os.path.expanduser("~/.qrl/client_config.json"),
    ]

    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> ClientConfig:
        """Load configuration from file or use defaults."""
        if config_path:
            # Specific config file provided
            if not Path(config_path).exists():
                raise FileNotFoundError(f"Configuration file not found: {config_path}")
            return cls._load_config_file(config_path)

        # Search for config files in default locations
        for path in cls.DEFAULT_CONFIG_PATHS:
            if Path(path).exists():
                try:
                    return cls._load_config_file(path)
                except Exception as e:
                    print(f"Warning: Failed to load config from {path}: {e}")
                    continue

        # Return default config if no file found
        return ClientConfig()

    @classmethod
    def _load_config_file(cls, config_path: str) -> ClientConfig:
        """Load configuration from a specific file."""
        path = Path(config_path)

        try:
            with open(path, 'r', encoding='utf-8') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    config_dict = yaml.safe_load(f) or {}
                elif path.suffix.lower() == '.json':
                    config_dict = json.load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {path.suffix}")

            config = ClientConfig.from_dict(config_dict)
            config.validate()
            return config

        except Exception as e:
            raise ValueError(f"Failed to load configuration from {config_path}: {e}")

    @classmethod
    def save_config(cls, config: ClientConfig, config_path: str) -> None:
        """Save configuration to file."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        config_dict = config.to_dict()

        try:
            with open(path, 'w', encoding='utf-8') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.safe_dump(config_dict, f, default_flow_style=False, indent=2)
                elif path.suffix.lower() == '.json':
                    json.dump(config_dict, f, indent=2)
                else:
                    raise ValueError(f"Unsupported config file format: {path.suffix}")

        except Exception as e:
            raise ValueError(f"Failed to save configuration to {config_path}: {e}")

    @classmethod
    def create_example_config(cls, config_path: str) -> None:
        """Create an example configuration file."""
        config = ClientConfig()
        cls.save_config(config, config_path)

        # Add comments if it's a YAML file
        if Path(config_path).suffix.lower() in ['.yaml', '.yml']:
            cls._add_yaml_comments(config_path)

    @classmethod
    def _add_yaml_comments(cls, config_path: str) -> None:
        """Add helpful comments to YAML config file."""
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Add header comment
        commented_content = """# QRL Client Configuration File
# This file contains default settings for the QRL client
# Adjust values as needed for your capture setup

""" + content

        # Add inline comments for key settings
        lines = commented_content.split('\n')
        commented_lines = []

        comments = {
            'monitor:': 'Monitor index (0 = primary monitor)',
            'interval:': 'Capture interval in seconds',
            'timeout:': 'Maximum capture time in seconds',
            'region:': 'Capture region [x, y, width, height], null = full screen',
            'progress_interval:': 'How often to show progress in seconds',
            'qr_detection_threshold:': 'QR detection sensitivity (0.0-1.0)',
            'image_preprocessing:': 'Enable image enhancement for better QR detection',
            'max_decode_attempts:': 'Maximum attempts to decode each QR',
            'log_level:': 'Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL',
        }

        for line in lines:
            new_line = line
            for key, comment in comments.items():
                if line.strip().startswith(key):
                    new_line = line + f'  # {comment}'
                    break
            commented_lines.append(new_line)

        commented_content = '\n'.join(commented_lines)

        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(commented_content)