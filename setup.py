#!/usr/bin/env python3
"""
QRL - QR Code Data Transfer PoC
Setup script for package installation
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file, 'r', encoding='utf-8') as f:
        requirements = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith('#')
        ]

setup(
    name="qrl",
    version="0.1.0",
    author="Mike Warner",
    author_email="minimike86@gmail.com",
    description="QR Code Data Transfer Proof of Concept",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/minimike86/QRL",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Education",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: Multimedia :: Graphics :: Capture :: Screen Capture",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "qrl-server=qrl_server.__main__:main",
            "qrl-client=qrl_client.__main__:main",
            "qrl-server-gui=qrl_server.gui:main",
            "qrl-client-gui=qrl_client.gui:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="qr-code transfer poc security-research red-team",
    project_urls={
        "Bug Reports": "https://github.com/minimike86/QRL/issues",
        "Source": "https://github.com/minimike86/QRL",
        "Documentation": "https://github.com/minimike86/QRL/tree/main/docs",
    },
)