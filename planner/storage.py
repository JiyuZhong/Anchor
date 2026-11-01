"""Read and write the local JSON save file."""

import json
import os
from pathlib import Path
import tempfile


class JsonRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "projects": [], "last_log_change": None}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Saved JSON is damaged. The file has not been replaced.") from exc
        if not isinstance(data, dict):
            raise ValueError("Unsupported save format. The file has not been replaced.")
        version = data.get("schema_version")
        if type(version) is not int or version != 1:
            raise ValueError("Unsupported save format. The file has not been replaced.")
        return data

    def save(self, data: dict) -> None:
        """Replace the save file after a full temporary write."""
        text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            # A file in the same folder can replace the old save atomically.
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=self.path.name + ".", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                # Flush both buffers before replacing the previous save.
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
