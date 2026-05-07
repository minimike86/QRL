"""
QRL Server - QR Code Data Transfer Server

Encodes and displays data as animated QR codes.
"""

__version__ = "0.1.0"
__author__ = "Mike"

from .encoder import QRLEncoder
from .qr_generator import QRGenerator
from .display import DisplayHandler

__all__ = ["QRLEncoder", "QRGenerator", "DisplayHandler"]
