# QRL: QR Code Data Exfiltration PoC

A proof-of-concept tool for exfiltrating data via animated QR codes displayed on a target machine's screen. The server chunks data into QR codes that flash in a repeating pattern, while a client application on another device captures and decodes these codes through remote desktop, VNC, Citrix, or similar screen capture methods.

## Features

- **Server-Side QR Generation**: Converts files or directory contents into sequential QR codes
- **Animated Display**: QR codes flash on screen in ordered, repeating patterns for reliable capture
- **Client-Side Decoder**: Reconstructs original data from captured QR code sequences
- **Flexible Data Sources**: Support for files, directories, and streaming data
- **Multiple Transport Methods**: Designed to work with remote desktop, VNC, Citrix, and other screen capture scenarios
- **Progress Tracking**: Visual feedback on encoding/decoding progress
- **Error Handling**: Built-in validation and error recovery mechanisms

## Concept

Traditional data exfiltration methods often trigger network monitoring and detection systems. QRL demonstrates a novel approach: encoding data into a visual sequence of QR codes displayed on screen, which can then be captured and reconstructed via any remote desktop connection or screen recording capability.

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
- `tkinter` or equivalent - GUI display (usually included with Python)

### Client
- Python 3.9+
- `opencv-python` - Screen capture and image processing
- `pyzbar` - QR code decoding
- `numpy` - Array operations
- `pillow` - Image handling

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

### Server Usage

```python
from qrl_server import QRLServer

# Initialize server
server = QRLServer(filename="path/to/file.txt", chunk_size=100)

# Start displaying QR codes
server.start_display()
```

Or via command line:

```bash
python -m qrl_server --file path/to/file.txt --chunk-size 100 --display-duration 2
```

### Client Usage

```python
from qrl_client import QRLClient

# Initialize client
client = QRLClient(output_file="recovered_file.txt")

# Start capturing and decoding
client.start_capture()
```

Or via command line:

```bash
python -m qrl_client --output recovered_file.txt --monitor-region 0,0,1920,1080
```

## Use Cases

- **Red Team Operations**: Data exfiltration without network detection
- **Security Research**: Testing air-gapped system vulnerabilities
- **Proof of Concept**: Demonstrating alternative data exfiltration vectors
- **Educational**: Understanding QR code encoding and data recovery techniques

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

- **Speed**: Slower than traditional network exfiltration
- **Distance**: Requires visual line of sight or screen capture access
- **Data Size**: Practical limits based on session duration and network stability
- **Screen Resolution**: Larger displays allow for bigger QR codes
- **Environmental Factors**: Lighting, camera quality affect capture reliability

## Similar Projects

- [QRxfil](https://github.com/OverkillGuy/qrxfil) - QR code based exfiltration to PDF
- [QRExfil](https://github.com/Shell-Company/QRExfil) - QR code exfiltration with GIF output

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

**Status**: Early PoC - Active Development
**Last Updated**: April 2026
