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
