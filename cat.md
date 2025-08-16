### lysergic

# Project Directory Structure
```
./
│   build.sh
│   requirements.txt
│   setup.py
│   README.md
│   LICENSE
├── lysergic/
├── │   lysergic.py
├── │   __init__.py
├── │   test_lysergic.py```

# README.md

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

# build.sh
#!/bin/bash

# Paths
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
MODULE_DIR="$DIR/$(basename $DIR)"

BLACK=black
BLACK_OPTS="--line-length 79"
LINTER=/usr/bin/flake8
GITIGNORE_URL="https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore"

# Update .gitignore if older than 30 days
GITIGNORE_PATH="$DIR/.gitignore"
if [ ! -f $GITIGNORE_PATH ] || [ `find $GITIGNORE_PATH -mtime +30` ]; then
    echo "Updating .gitignore"
    wget -O $GITIGNORE_PATH $GITIGNORE_URL 2>/dev/null
fi

# Run black
echo "Running black"
$BLACK $BLACK_OPTS $MODULE_DIR/*.py

# Run linter
echo "Running linter"
$LINTER $MODULE_DIR/*.py
if [ $? -ne 0 ]; then
    echo "Linting failed"
    exit 1
fi
echo "Linting passed"

# Run tests
echo "Running tests"
python3 -m unittest discover -s $MODULE_DIR
if [ $? -ne 0 ]; then
    echo "Tests failed"
    exit 1
fi

# Clean up
echo "Cleaning up"
find . -type d -name '__pycache__' -exec rm -r {} +
find . -type d -name '*.egg-info' -exec rm -r {} +

echo "Build successful"

exit 0

# setup.py
from setuptools import setup, find_packages
from lysergic import __program__, __version__

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name=__program__,
    version=__version__,
    author="Philip Orange",
    author_email="git@philiporange.com",
    description="A directory scanning tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/philiporange/lysergic",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    python_requires=">=3.6",
    install_requires=[
        "tqdm",
    ],
    extras_require={
        "magika": ["magika"],
        "dev": ["black", "flake8"],
    },
    entry_points={
        "console_scripts": [
            "lsd=lysergic.lysergic:main",
        ],
    },
)


# lysergic/lysergic.py
import os
import hashlib
import json
import gzip
from typing import Dict, Iterator, List
import random
import statistics
import time
import concurrent.futures
from pathlib import Path

from tqdm import tqdm


class LSD:
    BUFFER_SIZE = 1024 * 1024
    SAMPLE_SIZE = 1000

    def __init__(
        self,
        directory: str,
        include_metadata: bool = False,
        num_threads: int = 1,
        use_magika: bool = False,
        show_progress: bool = True,
        salt: str = "",
        disable_hashing: bool = False,
    ):
        self.directory = directory
        self.include_metadata = include_metadata
        self.num_threads = num_threads
        self.use_magika = use_magika
        self.show_progress = show_progress
        self.salt = salt
        self.magika = None
        self.output_to_file = (
            False  # New attribute to track output destination
        )
        self.disable_hashing = disable_hashing

        if self.use_magika:
            try:
                from magika import Magika

                self.magika = Magika()
            except ImportError:
                raise ImportError(
                    "Magika not found. Install with `pip install magika`"
                )

    def get_file_properties(self, file_path: str) -> Dict[str, str]:
        abs_path = os.path.join(self.directory, file_path)
        file_size = os.path.getsize(abs_path)

        _, extension = os.path.splitext(file_path)
        extension = extension.lstrip(".").lower()

        result = {
            "relative_path": file_path,
            "size": file_size,
            "extension": extension,
        }

        if not self.disable_hashing:
            md5 = hashlib.md5(self.salt.encode())
            sha1 = hashlib.sha1(self.salt.encode())
            sha256 = hashlib.sha256(self.salt.encode())

            with open(abs_path, "rb") as f:
                while True:
                    chunk = f.read(self.BUFFER_SIZE)
                    if not chunk:
                        break
                    md5.update(chunk)
                    sha1.update(chunk)
                    sha256.update(chunk)

            result["hashes"] = {
                "md5": md5.hexdigest(),
                "sha1": sha1.hexdigest(),
                "sha256": sha256.hexdigest(),
            }

        if self.magika:
            magika_result = self.magika.identify_path(Path(abs_path))
            result["magika"] = {
                "ct_label": magika_result.output.ct_label,
                "score": magika_result.output.score,
                "group": magika_result.output.group,
                "mime_type": magika_result.output.mime_type,
                "magic": magika_result.output.magic,
                "description": magika_result.output.description,
            }

        if self.include_metadata:
            stat = os.stat(abs_path)
            result["metadata"] = {
                "created": time.ctime(stat.st_ctime),
                "last_modified": time.ctime(stat.st_mtime),
                "last_accessed": time.ctime(stat.st_atime),
                "owner": stat.st_uid,
                "group": stat.st_gid,
                "permissions": oct(stat.st_mode)[-3:],
            }

        return result

    def count_files(self) -> int:
        return sum(len(files) for _, _, files in os.walk(self.directory))

    def estimate_processing_time(self) -> Dict[str, float]:
        all_files = self.get_all_files()
        total_files = len(all_files)

        if total_files <= self.SAMPLE_SIZE:
            sample_files = all_files
        else:
            sample_files = random.sample(all_files, self.SAMPLE_SIZE)

        processing_times = []
        pbar = tqdm(
            sample_files,
            desc="Estimating processing time",
            disable=not self.show_progress,
        )
        for file_path in pbar:
            start_time = time.time()
            self.get_file_properties(file_path)
            end_time = time.time()
            processing_times.append(end_time - start_time)

        avg_time = statistics.mean(processing_times)
        std_dev = (
            statistics.stdev(processing_times)
            if len(processing_times) > 1
            else 0
        )

        total_estimated_time = avg_time * total_files
        error_margin = (std_dev * total_files) / (len(processing_times) ** 0.5)

        return {
            "total_files": total_files,
            "sampled_files": len(sample_files),
            "avg_time_per_file": avg_time,
            "total_estimated_time": total_estimated_time,
            "error_margin": error_margin,
        }

    def get_all_files(self) -> List[str]:
        all_files = []
        for root, _, files in os.walk(self.directory):
            for file in files:
                all_files.append(
                    os.path.relpath(os.path.join(root, file), self.directory)
                )
        return all_files

    def process_directory(self) -> Iterator[Dict[str, str]]:
        all_files = self.get_all_files()
        total_files = len(all_files)
        use_progress_bar = self.output_to_file and self.show_progress

        with tqdm(
            total=total_files,
            desc="Processing files",
            unit="file",
            disable=not use_progress_bar,
        ) as pbar:
            if self.num_threads > 1:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.num_threads
                ) as executor:
                    for result in executor.map(
                        self.get_file_properties, all_files
                    ):
                        yield result
                        if use_progress_bar:
                            pbar.update(1)
            else:
                for file_path in all_files:
                    yield self.get_file_properties(file_path)
                    if use_progress_bar:
                        pbar.update(1)

    @staticmethod
    def save_to_jsonl(
        data_iterator: Iterator[Dict[str, str]],
        output_file: str,
        compress: bool = False,
    ):
        open_func = gzip.open if compress else open
        mode = "wt" if compress else "w"

        with open_func(output_file, mode) as f:
            for item in data_iterator:
                f.write(json.dumps(item) + "\n")

    def process_and_save(
        self, output_file: str = None, compress: bool = False
    ):
        self.output_to_file = (
            output_file is not None
        )  # Set the output destination
        data_iterator = self.process_directory()

        if output_file:
            self.save_to_jsonl(data_iterator, output_file, compress)
            print(f"Output saved to {output_file}")
        else:
            for item in data_iterator:
                print(json.dumps(item, indent=4))

    @staticmethod
    def format_time(seconds: float) -> str:
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Process directory and output file properties."
    )
    parser.add_argument("directory", help="Directory to process")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument(
        "-c",
        "--compress",
        action="store_true",
        help="Compress output with gzip",
    )
    parser.add_argument(
        "-m", "--metadata", action="store_true", help="Include file metadata"
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=1,
        help="Number of threads to use (default: 1)",
    )
    parser.add_argument(
        "--magika",
        action="store_true",
        help="Use Magika for file type detection",
    )
    parser.add_argument(
        "--eta", action="store_true", help="Estimate processing time"
    )
    parser.add_argument(
        "--no-progress", action="store_true", help="Disable progress bars"
    )
    parser.add_argument(
        "--salt",
        type=str,
        default="",
        help="Salt to prepend to file contents before hashing",
    )
    parser.add_argument(
        "--disable-hashing",
        action="store_true",
        help="Disable file hashing",
    )
    args = parser.parse_args()

    lsd = LSD(
        args.directory,
        args.metadata,
        args.threads,
        args.magika,
        not args.no_progress,
        args.salt,
        args.disable_hashing,
    )

    if args.eta:
        estimate = lsd.estimate_processing_time()
        estimate_time = estimate["total_estimated_time"]
        estimate_time_str = LSD.format_time(estimate_time)
        error_margin = estimate["error_margin"]
        error_margin_str = LSD.format_time(error_margin)

        print("Estimated processing time:")
        print(f"Total files: {estimate['total_files']}")
        print(f"Sampled files: {estimate['sampled_files']}")
        print(
            f"Average time: {estimate['avg_time_per_file']:.4f} seconds/file"
        )
        print(
            f"Total estimated time: {estimate_time_str} ± {error_margin_str}"
        )
    else:
        lsd.process_and_save(args.output, args.compress)


if __name__ == "__main__":
    main()


# lysergic/__init__.py
from .lysergic import LSD

__program__ = "lysergic"
__version__ = "0.1.5"

__all__ = ["LSD"]


# lysergic/test_lysergic.py
import unittest
import os
import tempfile
import shutil
import random
import json

from lysergic import LSD


def create_complex_test_directory(
    base_path, num_dirs=25, max_depth=5, num_files=150
):
    # Create base directory
    os.makedirs(base_path, exist_ok=True)

    # Create directory structure
    dirs = [base_path]
    for _ in range(
        num_dirs - 1
    ):  # -1 because we already created the base directory
        parent = random.choice(dirs)
        depth = len(parent.split(os.path.sep)) - len(
            base_path.split(os.path.sep)
        )
        if depth < max_depth:
            new_dir = os.path.join(parent, f"dir_{len(dirs)}")
            os.makedirs(new_dir)
            dirs.append(new_dir)

    # Ensure at least one empty directory
    empty_dir = os.path.join(random.choice(dirs), "empty_dir")
    os.makedirs(empty_dir)

    # Create and populate files
    created_files = []
    for i in range(num_files):
        parent = random.choice(dirs)
        file_path = os.path.join(parent, f"file_{i}.bin")
        size = random.randint(1, 100 * 1024)  # Random size up to 100KB
        with open(file_path, "wb") as f:
            f.write(os.urandom(size))
        created_files.append(file_path)

    return dirs, created_files


class TestLSDClass(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.dirs, cls.created_files = create_complex_test_directory(
            cls.temp_dir
        )
        # Disable progress bars for all LSD instances used in tests
        cls.lsd = LSD(cls.temp_dir, show_progress=False)
        cls.lsd_with_metadata = LSD(
            cls.temp_dir, include_metadata=True, show_progress=False
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir)

    def test_get_file_properties(self):
        test_file = self.created_files[0]
        relative_path = os.path.relpath(test_file, self.temp_dir)
        result = self.lsd.get_file_properties(relative_path)

        self.assertEqual(result["relative_path"], relative_path)
        self.assertGreater(result["size"], 0)
        self.assertEqual(result["extension"], "bin")
        self.assertIn("md5", result["hashes"])
        self.assertIn("sha1", result["hashes"])
        self.assertIn("sha256", result["hashes"])

    def test_get_file_properties_with_metadata(self):
        test_file = self.created_files[0]
        relative_path = os.path.relpath(test_file, self.temp_dir)
        result = self.lsd_with_metadata.get_file_properties(relative_path)

        self.assertIn("metadata", result)
        self.assertIn("created", result["metadata"])
        self.assertIn("last_modified", result["metadata"])
        self.assertIn("last_accessed", result["metadata"])
        self.assertIn("owner", result["metadata"])
        self.assertIn("group", result["metadata"])
        self.assertIn("permissions", result["metadata"])

    def test_count_files(self):
        count = self.lsd.count_files()
        self.assertEqual(
            count, 150
        )  # We created 150 files in our complex directory

    def test_get_all_files(self):
        files = self.lsd.get_all_files()
        self.assertEqual(
            len(files), 150
        )  # We created 150 files in our complex directory

        # Check if all created files are in the result
        relative_created_files = [
            os.path.relpath(f, self.temp_dir) for f in self.created_files
        ]
        self.assertTrue(all(f in files for f in relative_created_files))

    def test_format_time(self):
        self.assertEqual(LSD.format_time(3661), "01:01:01")
        self.assertEqual(LSD.format_time(7200), "02:00:00")
        self.assertEqual(LSD.format_time(45), "00:00:45")

    def test_estimate_processing_time(self):
        estimate = self.lsd.estimate_processing_time()

        self.assertEqual(estimate["total_files"], 150)
        self.assertLessEqual(
            estimate["sampled_files"], 150
        )  # It should be either 150 or SAMPLE_SIZE (1000)
        self.assertGreater(estimate["avg_time_per_file"], 0)
        self.assertGreater(estimate["total_estimated_time"], 0)
        self.assertGreaterEqual(estimate["error_margin"], 0)

    def test_process_directory(self):
        results = list(self.lsd.process_directory())
        self.assertEqual(
            len(results), 150
        )  # We created 150 files in our complex directory

        # Check if all files have been processed
        processed_paths = [result["relative_path"] for result in results]
        self.assertTrue(
            all(
                os.path.relpath(f, self.temp_dir) in processed_paths
                for f in self.created_files
            )
        )

    def test_save_to_jsonl(self):
        test_data = [{"key1": "value1"}, {"key2": "value2"}]
        test_output = os.path.join(self.temp_dir, "test_output.jsonl")

        LSD.save_to_jsonl(iter(test_data), test_output)

        with open(test_output, "r") as f:
            loaded_data = [json.loads(line.strip()) for line in f]

        self.assertEqual(test_data, loaded_data)

    def test_empty_directory(self):
        empty_dir = os.path.join(self.temp_dir, "empty_dir")
        empty_lsd = LSD(empty_dir, show_progress=False)

        files = empty_lsd.get_all_files()
        self.assertEqual(len(files), 0)

        count = empty_lsd.count_files()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()


