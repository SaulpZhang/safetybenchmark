from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from safetybenchmark.agents import load_dotenv


class AgentConfigurationTests(unittest.TestCase):
    def test_dotenv_loader_supports_llm_configuration_without_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "BASE_URL=https://llm.invalid/v1\nAPI_KEY=test-only\nMODEL=test-model\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_dotenv(path),
                {
                    "BASE_URL": "https://llm.invalid/v1",
                    "API_KEY": "test-only",
                    "MODEL": "test-model",
                },
            )


if __name__ == "__main__":
    unittest.main()
