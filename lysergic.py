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

        result = {
            "relative_path": file_path,
            "size": file_size,
            "extension": extension,
            "hashes": {
                "md5": md5.hexdigest(),
                "sha1": sha1.hexdigest(),
                "sha256": sha256.hexdigest(),
            },
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
    args = parser.parse_args()

    lsd = LSD(
        args.directory,
        args.metadata,
        args.threads,
        args.magika,
        not args.no_progress,
        args.salt,
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
