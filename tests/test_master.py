import os
import tempfile
import unittest
from unittest.mock import patch

from src import master


class DownloadMasterFileTests(unittest.TestCase):
    def test_download_master_file_returns_false_when_download_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(master, "MASTER_FILE", os.path.join(tmpdir, "fostkcode.mst")), \
                 patch.object(master, "MASTER_ZIP", os.path.join(tmpdir, "fostkcode.mst.zip")), \
                 patch.object(master, "MASTER_URL", "https://example.invalid/fostkcode.mst.zip"), \
                 patch("src.master.urllib.request.urlopen", side_effect=TimeoutError("slow download")), \
                 patch("src.master.os.makedirs"):
                result = master.download_master_file()

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
