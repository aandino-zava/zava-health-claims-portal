"""Fetch pinned redistributable browser assets from npm, verifying registry integrity."""

import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path
from urllib.request import urlopen

TARGET = Path(__file__).resolve().parents[1] / "app" / "static" / "vendor"
PACKAGES = {
    "bootstrap": (
        "5.3.8",
        {"package/dist/css/bootstrap.min.css": "bootstrap.min.css", "package/LICENSE": "bootstrap.LICENSE"},
    ),
    "@azure/msal-browser": (
        "4.25.0",
        {"package/lib/msal-browser.min.js": "msal-browser.min.js", "package/LICENSE": "msal.LICENSE"},
    ),
}


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    records = {}
    for name, (version, files) in PACKAGES.items():
        with urlopen(f"https://registry.npmjs.org/{name}/{version}", timeout=30) as response:
            metadata = json.load(response)
        with urlopen(metadata["dist"]["tarball"], timeout=30) as response:
            data = response.read()
        integrity = metadata["dist"]["integrity"]
        algorithm, expected = integrity.split("-", 1)
        if algorithm != "sha512" or base64.b64encode(hashlib.sha512(data).digest()).decode() != expected:
            raise RuntimeError(f"Integrity check failed for {name}")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for source, dest in files.items():
                # Read individual known members; never extract arbitrary archive paths.
                contents = archive.extractfile(source).read()
                (TARGET / dest).write_bytes(contents)
        records[name] = {"version": version, "integrity": integrity}
    (TARGET / "manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
