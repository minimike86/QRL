#!/usr/bin/env python3
"""
Configuration management for QRL server.
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class ServerConfig:
    """Server configuration settings."""

    # File settings — chunk_size is the raw bytes per chunk (header is added on top).
    # Default to "Robust" (H-level error correction): tolerates ~30% damage vs
    # 25% for Q level. Screen-captured QRs benefit substantially because of
    # JPEG-style compression artefacts, monitor backlight bleed, and partial
    # occlusion from cursors/notifications. 1264 = H binary-mode v40 cap (1273) - 9 (header).
    chunk_size: int = 1264
    error_correction: str = "H"

    # Display settings — 0.1s = 10 FPS, a good balance between throughput and
    # what a typical screen-capture client can reliably read.
    duration: float = 0.1
    repeat: bool = True
    window_title: str = "QRL Server"
    window_width: int = 800
    window_height: int = 600
    fullscreen: bool = False

    # Multi-QR grid settings for higher throughput. cols/rows are independent
    # (e.g. 2x4 = 2 wide, 4 tall = 8 streams). qr_grid_auto overrides cols/rows
    # at display time by fitting as many cells as the screen allows.
    qr_grid_cols: int = 1
    qr_grid_rows: int = 1
    qr_grid_auto: bool = False
    qr_physical_size: int = 400  # Physical size of each QR code in pixels

    # Pre-generate every QR image upfront (faster display, more memory).
    # Auto-disabled for files larger than `prefetch_max_bytes`.
    prefetch_qr_images: bool = True
    prefetch_max_bytes: int = 5 * 1024 * 1024  # 5 MB

    # QR settings
    qr_version: Optional[int] = None
    qr_border: int = 6  # quiet zone in modules — wider than the 4-module spec minimum
    qr_box_size: int = 10

    # Output settings
    save_qr: Optional[str] = None
    output_format: str = "PNG"

    # Advanced settings
    compression_level: int = 6
    max_file_size: int = 100 * 1024 * 1024  # 100MB

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ServerConfig':
        """Create config from dictionary, filtering unknown keys."""
        valid_keys = {field.name for field in cls.__dataclass_fields__.values()}
        filtered_dict = {k: v for k, v in config_dict.items() if k in valid_keys}

        # Legacy migration: pre-2026 configs used a single `qr_grid_size: int`
        # for square N×N grids. Map it to the new cols/rows/auto trio when the
        # new keys are absent.
        legacy = config_dict.get("qr_grid_size")
        if legacy is not None:
            if "qr_grid_cols" not in filtered_dict:
                filtered_dict["qr_grid_cols"] = int(legacy)
            if "qr_grid_rows" not in filtered_dict:
                filtered_dict["qr_grid_rows"] = int(legacy)

        return cls(**filtered_dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    def validate(self) -> bool:
        """Validate configuration values."""
        errors = []

        if self.chunk_size <= 0 or self.chunk_size > 65536:
            errors.append("chunk_size must be between 1 and 65536")

        if self.error_correction not in ["L", "M", "Q", "H"]:
            errors.append("error_correction must be one of: L, M, Q, H")

        # Validate chunk size against QR capacity
        from .qr_generator import QRGenerator
        if not QRGenerator.validate_chunk_size(self.chunk_size, self.error_correction):
            max_size = QRGenerator.get_max_chunk_size(self.error_correction)
            errors.append(f"chunk_size ({self.chunk_size}) exceeds QR capacity for error level '{self.error_correction}' (max: {max_size})")

        if self.duration <= 0 or self.duration > 60:
            errors.append("duration must be between 0.01 and 60 seconds")

        if self.qr_version is not None and (self.qr_version < 1 or self.qr_version > 40):
            errors.append("qr_version must be between 1 and 40")

        if self.qr_border < 0:
            errors.append("qr_border must be non-negative")

        if self.qr_box_size <= 0:
            errors.append("qr_box_size must be positive")

        if self.compression_level < 0 or self.compression_level > 9:
            errors.append("compression_level must be between 0 and 9")

        if self.max_file_size <= 0:
            errors.append("max_file_size must be positive")

        # Independent col/row caps. Auto-fit ignores these at display time
        # since it sizes to the actual screen.
        if self.qr_grid_cols < 1 or self.qr_grid_cols > 32:
            errors.append("qr_grid_cols must be between 1 and 32")
        if self.qr_grid_rows < 1 or self.qr_grid_rows > 32:
            errors.append("qr_grid_rows must be between 1 and 32")
        # ParallelQREncoder caps total streams at 254 (1-byte stream id space).
        if self.qr_grid_cols * self.qr_grid_rows > 254:
            errors.append("qr_grid_cols × qr_grid_rows must not exceed 254")

        if self.qr_physical_size <= 50 or self.qr_physical_size > 1000:
            errors.append("qr_physical_size must be between 50 and 1000 pixels")

        if self.prefetch_max_bytes <= 0:
            errors.append("prefetch_max_bytes must be positive")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

        return True


class ConfigManager:
    """Manages loading and saving configuration files."""

    DEFAULT_CONFIG_PATHS = [
        "qrl_server.yaml",
        "qrl_server.yml",
        "qrl_server.json",
        "config/qrl_server.yaml",
        "config/qrl_server.yml",
        "config/qrl_server.json",
        os.path.expanduser("~/.qrl/server_config.yaml"),
        os.path.expanduser("~/.qrl/server_config.yml"),
        os.path.expanduser("~/.qrl/server_config.json"),
    ]

    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> ServerConfig:
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
        return ServerConfig()

    @classmethod
    def _load_config_file(cls, config_path: str) -> ServerConfig:
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

            config = ServerConfig.from_dict(config_dict)
            config.validate()
            return config

        except Exception as e:
            raise ValueError(f"Failed to load configuration from {config_path}: {e}")

    @classmethod
    def save_config(cls, config: ServerConfig, config_path: str) -> None:
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
        config = ServerConfig()
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
        commented_content = """# QRL Server Configuration File
# This file contains default settings for the QRL server
# Adjust values as needed for your use case

""" + content

        # Add inline comments for key settings
        lines = commented_content.split('\n')
        commented_lines = []

        comments = {
            'chunk_size:': 'Size of data chunks in bytes (affects QR capacity)',
            'error_correction:': 'QR error correction level: L, M, Q, H (higher = more robust)',
            'duration:': 'Display time per QR code in seconds',
            'repeat:': 'Whether to repeat the QR sequence continuously',
            'window_title:': 'Title of the display window',
            'qr_version:': 'QR code version (1-40), null = auto-detect',
            'max_file_size:': 'Maximum file size to process (bytes)',
            'qr_grid_cols:': 'Display grid width (1-32)',
            'qr_grid_rows:': 'Display grid height (1-32)',
            'qr_grid_auto:': 'Override cols/rows by fitting as many cells as the screen allows',
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