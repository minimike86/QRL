# QRL API Reference

## Server API

### QRLEncoder

Main class for encoding files into QR code sequences.

```python
from qrl_server import QRLEncoder

encoder = QRLEncoder(
    source_path: str,
    chunk_size: int = 1024,
    qr_version: int = None,
    error_correction: str = "Q"
)
```

#### Parameters

- `source_path` (str): Path to file or directory to encode
- `chunk_size` (int): Size of each data chunk in bytes (default: 1024)
- `qr_version` (int): QR code version 1-40, None for auto (default: None)
- `error_correction` (str): Error correction level: L/M/Q/H (default: Q)

#### Methods

- `encode() → List[Image]`: Returns list of PIL Image objects containing QR codes
- `get_metadata() → dict`: Returns encoding metadata (total_chunks, chunk_size, etc.)
- `validate() → bool`: Validates source file integrity

### QRGenerator

Low-level QR code generation.

```python
from qrl_server import QRGenerator

generator = QRGenerator(
    data: bytes,
    version: int = None,
    error_correction: str = "Q"
)
```

#### Methods

- `generate() → Image`: Returns PIL Image of QR code
- `get_capacity(version: int) → int`: Returns max bytes for QR version

### DisplayHandler

Displays QR codes on screen.

```python
from qrl_server import DisplayHandler

display = DisplayHandler(
    qr_images: List[Image],
    duration: float = 2.0,
    repeat: bool = True,
    window_title: str = "QRL"
)
```

#### Methods

- `start() → None`: Start display loop
- `stop() → None`: Stop display
- `set_duration(duration: float) → None`: Update display timing
- `is_running() → bool`: Check if display is active

## Client API

### QRLDecoder

Main class for decoding QR code sequences.

```python
from qrl_client import QRLDecoder

decoder = QRLDecoder(
    output_path: str,
    timeout: int = 300
)
```

#### Parameters

- `output_path` (str): Path to write decoded file
- `timeout` (int): Timeout in seconds for capture (default: 300)

#### Methods

- `decode(frames: List[Image]) → bool`: Decode from list of frames
- `get_progress() → dict`: Returns {total_chunks, decoded_chunks, percentage}
- `get_missing_chunks() → List[int]`: Returns list of missing chunk numbers

### QRReader

QR code detection and decoding.

```python
from qrl_client import QRReader

reader = QRReader()
```

#### Methods

- `read(image: Image) → Optional[bytes]`: Attempt to read QR from image
- `read_multiple(image: Image) → List[bytes]`: Read multiple QR codes from single image
- `get_confidence() → float`: Confidence of last read (0.0-1.0)

### CaptureHandler

Screen capture management.

```python
from qrl_client import CaptureHandler

capture = CaptureHandler(
    monitor: int = 0,
    region: Tuple[int, int, int, int] = None,
    interval: float = 0.5
)
```

#### Parameters

- `monitor` (int): Monitor index (0 = primary)
- `region` (Tuple): (x, y, width, height) capture region
- `interval` (float): Seconds between capture frames

#### Methods

- `start() → None`: Start capturing
- `stop() → None`: Stop capturing
- `get_frames() → List[Image]`: Get captured frames since last call
- `set_region(region: Tuple) → None`: Update capture region

## Command Line Interface

### Server

```bash
python -m qrl_server [OPTIONS]

Options:
  --file PATH             Input file path (required)
  --chunk-size INT        Chunk size in bytes (default: 1024)
  --qr-version INT        QR version 1-40 (auto)
  --duration FLOAT        Display duration per QR (default: 2.0)
  --repeat                Repeat pattern (default: True)
  --help                  Show help
```

### Client

```bash
python -m qrl_client [OPTIONS]

Options:
  --output PATH           Output file path (required)
  --monitor INT           Monitor index (default: 0)
  --region "x,y,w,h"      Capture region (auto-detect)
  --timeout INT           Timeout in seconds (default: 300)
  --help                  Show help
```

## Error Handling

Both server and client use custom exceptions:

```python
from qrl_server import QRLError, EncodingError
from qrl_client import DecodingError, CaptureError
```

## Logging

Enable logging with:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```
