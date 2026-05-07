# QRL: QR Code PoC

A proof-of-concept tool for generating animated QR codes displayed on a target machine's screen. The server chunks data into QR codes that flash in a repeating pattern, while a client application on another device captures and decodes these codes through remote desktop, VNC, Citrix, or similar screen capture methods.

## Features

- **Server-Side QR Generation**: Converts files or directory contents into sequential QR codes
- **Animated Display**: QR codes flash on screen in ordered, repeating patterns for reliable capture
- **Client-Side Decoder**: Reconstructs original data from captured QR code sequences
- **GUI Applications**: Easy-to-use graphical interfaces for both server and client
- **Configuration Files**: YAML/JSON configuration support with comprehensive settings
- **Enhanced Error Handling**: Robust error handling and recovery mechanisms
- **Flexible Data Sources**: Support for files, directories, and streaming data
- **Multiple Transport Methods**: Designed to work with remote desktop, VNC, Citrix, and other screen capture scenarios
- **Progress Tracking**: Visual feedback on encoding/decoding progress with detailed statistics
- **Advanced QR Settings**: Configurable QR versions, error correction levels, and display options

## Concept

Traditional data generation methods often trigger network monitoring and detection systems. QRL demonstrates a novel approach: encoding data into a visual sequence of QR codes displayed on screen, which can then be captured and reconstructed via any remote desktop connection or screen recording capability.

### How It Works

1. **Server**: User specifies a file or directory
2. **Chunking**: Data is chunked into appropriately sized pieces
3. **QR Encoding**: Each chunk is encoded into a QR code
4. **Display**: QR codes flash on screen in sequence, repeatedly
5. **Client**: Another device captures the screen and reads the QR codes
6. **Reconstruction**: Client rebuilds the original file from decoded chunks

## Architecture

```
qrl/
├── qrl_server/          # Server-side encoder and display logic
│   ├── __init__.py
│   ├── encoder.py       # Core encoding logic
│   ├── qr_generator.py  # QR code generation
│   ├── display.py       # Screen display handler
│   └── chunk.py         # Data chunking utilities
├── qrl_client/          # Client-side decoder and capture logic
│   ├── __init__.py
│   ├── decoder.py       # Core decoding logic
│   ├── qr_reader.py     # QR code reading and OCR
│   └── capture.py       # Screen capture handler
├── docs/                # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── EXAMPLES.md
├── examples/            # Example scripts and configurations
│   ├── basic_server.py
│   └── basic_client.py
├── tests/               # Unit and integration tests
│   ├── test_encoder.py
│   ├── test_decoder.py
│   ├── test_chunking.py
│   └── test_qr_generation.py
├── assets/              # Images, diagrams, logos
│   └── architecture.png
├── requirements.txt     # Python dependencies
├── setup.py             # Package installation
├── LICENSE              # MIT License
└── README.md           # This file
```

## Requirements

### Server
- Python 3.9+
- `qrcode[pil]` - QR code generation
- `pillow` - Image handling
- `PyYAML` - Configuration file support
- `tkinter` - GUI interface (usually included with Python)

### Client
- Python 3.9+
- `opencv-python` - Screen capture and image processing
- `pyzbar` - QR code decoding
- `numpy` - Array operations
- `pillow` - Image handling
- `PyYAML` - Configuration file support
- `tkinter` - GUI interface (usually included with Python)

### Optional
- `pytest` - For running tests
- `black` - Code formatting
- `flake8` - Code linting

## Installation

### From Source

```bash
git clone https://github.com/minimike86/QRL.git
cd QRL
pip install -r requirements.txt
```

### Development Setup

```bash
git clone https://github.com/minimike86/QRL.git
cd QRL
pip install -e .
pip install -r requirements-dev.txt
```

## Quick Start

### GUI Mode (Recommended)

Launch the graphical interfaces for easy configuration:

```bash
# Server GUI
qrl-server-gui
# or
python -m qrl_server --gui

# Client GUI
qrl-client-gui
# or
python -m qrl_client --gui
```

### Command Line Usage

#### Server

Basic usage:
```bash
# Encode and display a file
qrl-server path/to/file.txt

# With custom settings
qrl-server path/to/file.txt --chunk-size 2048 --duration 1.5 --error-correction H
```

Using configuration files:
```bash
# Create example config
qrl-server --create-config my_config.yaml

# Use configuration file
qrl-server --config my_config.yaml path/to/file.txt

# Override config settings
qrl-server --config my_config.yaml --duration 3.0 path/to/file.txt
```

#### Client

Basic usage:
```bash
# Capture and decode QR codes
qrl-client --output recovered_file.txt

# With custom capture region
qrl-client --output recovered_file.txt --region 100,100,800,600
```

Using configuration files:
```bash
# Create example config
qrl-client --create-config my_config.yaml

# Use configuration file
qrl-client --config my_config.yaml --output recovered_file.txt

# Advanced settings
qrl-client --config advanced.yaml --output file.txt --verbose --save-progress
```

### Python API

You can also use QRL programmatically:

```python
from qrl_server.encoder import QRLEncoder
from qrl_server.display import DisplayHandler

# Server: Encode and display
encoder = QRLEncoder("path/to/file.txt", chunk_size=1024)
qr_images = encoder.encode()
display = DisplayHandler(qr_images, duration=2.0)
display.start()
```

```python
from qrl_client.capture import CaptureHandler
from qrl_client.decoder import QRLDecoder

# Client: Capture and decode
capture = CaptureHandler(monitor=0)
decoder = QRLDecoder("output.txt")
capture.start()
# ... decode frames as they come in
```

## Configuration Files

QRL supports YAML and JSON configuration files for both server and client applications. Configuration files are automatically searched in the following locations:

1. Current directory: `qrl_server.yaml`, `qrl_client.yaml`
2. `config/` subdirectory
3. User home directory: `~/.qrl/server_config.yaml`, `~/.qrl/client_config.yaml`

### Example Server Configuration

```yaml
# Server settings
chunk_size: 2048
error_correction: H
duration: 1.5
repeat: true
window_title: "QRL Server - Production"

# QR settings
qr_version: 10
qr_border: 4
qr_box_size: 15

# Advanced options
max_file_size: 104857600  # 100MB
compression_level: 6
```

### Example Client Configuration

```yaml
# Capture settings
monitor: 0
interval: 0.3
timeout: 600
region: [100, 100, 1200, 800]  # x, y, width, height

# Detection settings
qr_detection_threshold: 0.4
image_preprocessing: true
enhance_contrast: true
max_decode_attempts: 8

# Processing
save_progress: true
progress_interval: 2.0
```

### Managing Configurations

```bash
# Create example configuration files
qrl-server --create-config config/server.yaml
qrl-client --create-config config/client.yaml

# Save current CLI settings to config
qrl-server --chunk-size 4096 --duration 1.0 --save-config my_settings.yaml

# Load and modify settings
qrl-client --config base.yaml --monitor 1 --timeout 900 --save-config modified.yaml
```

## Use Cases

- **Red Team Operations**: Data transfer without network detection
- **Security Research**: Testing air-gapped system vulnerabilities
- **Proof of Concept**: Demonstrating alternative data transfer vectors
- **Educational**: Understanding QR code encoding and data recovery techniques
- **Backup and Recovery**: Novel approach to data backup via visual encoding

## Technical Details

### Data Chunking Strategy
Data is split into chunks sized to fit QR code capacity limitations. Chunk size varies based on:
- QR code version (1-40)
- Error correction level (L, M, Q, H)
- Data encoding (numeric, alphanumeric, byte, kanji)

### Display Sequence
QR codes display in a repeating cycle to ensure capture:
1. Display each QR code for N seconds
2. Optional inter-code delay
3. Repeat cycle until client acknowledges receipt

### Error Detection
- Frame numbering ensures sequence integrity
- CRC checksums validate chunk integrity
- Missing chunk detection and retry logic

## Limitations

- **Speed**: Slower than traditional network transfer
- **Distance**: Requires visual line of sight or screen capture access
- **Data Size**: Practical limits based on session duration and network stability
- **Screen Resolution**: Larger displays allow for bigger QR codes
- **Environmental Factors**: Lighting, camera quality affect capture reliability

## Similar Projects

- [QRxfil](https://github.com/OverkillGuy/qrxfil) - QR code based transfer to PDF
- [QRExfil](https://github.com/Shell-Company/QRExfil) - QR code transfer with GIF output

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is provided for educational and authorized security testing purposes only. Unauthorized access to computer systems is illegal. Users are responsible for complying with all applicable laws and obtaining proper authorization before use.

## Support

For issues, questions, or suggestions:
- Open an GitHub issue
- Check existing documentation in `/docs`
- Review examples in `/examples`

---

## Recent Updates

- ✅ **GUI Applications**: Full-featured graphical interfaces for both server and client
- ✅ **Configuration System**: YAML/JSON configuration file support with validation
- ✅ **Enhanced CLI**: Improved command-line interfaces with comprehensive options
- ✅ **Error Handling**: Robust error handling and recovery mechanisms
- ✅ **Documentation**: Complete usage examples and configuration guides

**Status**: Feature-Complete PoC - Ready for Use
**Last Updated**: May 2026
