"""
QRL - QR Code Data Exfiltration PoC

Setup configuration for package installation.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    long_description = readme_file.read_text(encoding="utf-8")

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip()
        for line in requirements_file.read_text(encoding="utf-8").split("\n")
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="qrl",
    version="0.1.0",
    description="QR Code Data Exfiltration Proof of Concept",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Mike",
    author_email="minimike86@gmail.com",
    url="https://github.com/minimike86/QRL",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
    ],
    keywords="qr-code exfiltration security poc data-transfer",
    project_urls={
        "Bug Reports": "https://github.com/minimike86/QRL/issues",
        "Documentation": "https://github.com/minimike86/QRL/docs",
        "Source Code": "https://github.com/minimike86/QRL",
    },
    entry_points={
        "console_scripts": [
            "qrl-server=qrl_server.__main__:main",
            "qrl-client=qrl_client.__main__:main",
        ],
    },
)
