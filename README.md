# Lysergic

Lysergic is a directory scanning tool. It allows you to quickly analyze file systems, compute file hashes, and extract metadata. It includes support for multi-threading and optional Magika integration for advanced file type detection.

## Installation

You can install Lysergic using pip:

```bash
pip install lysergic
```

For Magika support, install with the 'magika' extra:

```bash
pip install lysergic[magika]
```

## Command Line Usage

After installation, you can use Lysergic from the command line with the `lsd` command:

```bash
lsd /path/to/directory
```

Optional arguments:

- `-o, --output FILE`: Specify output file (default: stdout)
- `-c, --compress`: Compress output with gzip
- `-m, --metadata`: Include file metadata
- `-t, --threads N`: Number of threads to use (default: 1)
- `--magika`: Use Magika for file type detection
- `--eta`: Estimate processing time
- `--no-progress`: Disable progress bars
- `--salt STRING`: Salt to prepend to file contents before hashing

Example:

```bash
lsd /home/user/documents -o output.jsonl -c -m -t 4 --magika
```

This command will scan the `/home/user/documents` directory, include metadata, use 4 threads, enable Magika, and save the compressed output to `output.jsonl.gz`.

## Python Module Usage

You can also use Lysergic as a Python module in your scripts:

```python
from lysergic import LSD

# Initialize LSD
lsd = LSD("/path/to/directory", include_metadata=True, num_threads=4, use_magika=True)

# Process the directory and iterate over results
for file_info in lsd.process_directory():
    print(file_info)

# Or process and save to a file
lsd.process_and_save("output.jsonl", compress=True)

# Estimate processing time
estimate = lsd.estimate_processing_time()
print(f"Estimated time: {LSD.format_time(estimate['total_estimated_time'])}")
```

## License

This project is licensed under the Creative Commons Zero v1.0 Universal (CC0-1.0) License. This means you can copy, modify, distribute, and perform the work, even for commercial purposes, all without asking permission.