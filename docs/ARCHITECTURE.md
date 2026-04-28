# QRL Architecture

## Overview

QRL is a two-component system: a server that encodes data into QR codes and a client that captures and decodes them.

## Server Architecture

### Components

1. **Encoder** (`encoder.py`)
   - Accepts file paths or directory paths
   - Manages chunking and sequence numbering
   - Coordinates with QR generator

2. **QR Generator** (`qr_generator.py`)
   - Creates QR codes from byte data
   - Handles different QR versions and error correction levels
   - Optimizes chunk size based on available QR capacity

3. **Display Handler** (`display.py`)
   - Manages full-screen QR code display
   - Controls timing and animation cycles
   - Provides progress feedback

4. **Chunking** (`chunk.py`)
   - Splits large files into appropriately sized chunks
   - Manages metadata (sequence numbers, checksums)
   - Handles reassembly logic on client side

## Client Architecture

### Components

1. **Decoder** (`decoder.py`)
   - Manages overall decoding process
   - Validates and reassembles chunks in correct order
   - Handles missing chunk detection and retry logic

2. **QR Reader** (`qr_reader.py`)
   - Uses computer vision to detect QR codes
   - Decodes QR data to byte sequences
   - Provides confidence metrics for decoded data

3. **Capture Handler** (`capture.py`)
   - Captures screen regions at specified intervals
   - Detects new QR codes in sequence
   - Manages frame synchronization

## Data Flow

### Server → Display

```
File Input
    ↓
Chunking (add metadata)
    ↓
QR Generation (bytes → QR codes)
    ↓
Display Loop (repeat until complete)
```

### Client → Reconstruction

```
Screen Capture (video frames)
    ↓
QR Detection (find QR in frame)
    ↓
QR Decoding (QR → bytes)
    ↓
Chunk Validation (verify sequence/checksum)
    ↓
Reassembly (reorder chunks)
    ↓
File Output
```

## Chunk Format

```
[Metadata: 4 bytes] [Sequence: 4 bytes] [Data: variable] [Checksum: 4 bytes]
```

- **Metadata**: Flags, version info
- **Sequence**: Frame number (0-indexed)
- **Data**: Actual file data
- **Checksum**: CRC32 validation

## QR Code Encoding

- **Version**: 1-40 (size determined by data size)
- **Error Correction**: Q (25%) - balance between capacity and reliability
- **Data Mode**: Byte mode for maximum flexibility
- **Max Capacity**: ~2953 bytes per QR code (version 40, Q correction)

## Security Considerations

- **No Encryption**: Data is unencrypted in QR codes
- **Visual Detection**: Requires line of sight or screen capture access
- **No Authentication**: No built-in authentication mechanism
- **Timing Analysis**: Sequential display could be detected via monitoring

## Performance Characteristics

- **Encoding**: ~1-10ms per QR code (depends on data size)
- **Display**: 1-5 seconds per code (configurable)
- **Decoding**: ~50-200ms per QR code (depends on image quality)
- **Throughput**: ~100-500 bytes per second (practical limit)

## Future Enhancements

- Parallel QR display (multiple codes at once)
- Encryption layer
- Redundancy/error correction codes (Reed-Solomon)
- Compression before encoding
- Resume capability for interrupted transfers
