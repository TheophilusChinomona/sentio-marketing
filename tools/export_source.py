"""Bundle committed corresponding source, excluding runtime files and tenant data."""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--crm-repo", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("Output exists")
    roots = {
        "crm": a.crm_repo.resolve(),
        "sentio_marketing": Path(__file__).resolve().parents[1],
    }
    entries = {}
    revisions = {}
    for label, root in roots.items():
        if subprocess.check_output(
            ["git", "-C", str(root), "diff", "--name-only", "HEAD"]
        ).strip():
            p.error("Commit tracked changes before exporting " + label)
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        revisions[label] = sha
        archive = subprocess.check_output(
            ["git", "-C", str(root), "archive", "--format=tar", "HEAD"]
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar:
                if not member.isfile():
                    continue
                name = member.name
                parts = Path(name).parts
                if any(
                    x in {"clients", "private", ".git", ".venv", "node_modules"}
                    for x in parts
                ) or any(
                    x.startswith(".env") and not x.endswith(".example") for x in parts
                ):
                    p.error("Sensitive runtime path in tracked source: " + name)
                entries[label + "/" + name] = tar.extractfile(member).read()
    manifest = {
        "revisions": revisions,
        "files": [
            {"path": n, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
            for n, b in sorted(entries.items())
        ],
    }
    entries["SOURCE-MANIFEST.json"] = json.dumps(manifest, indent=2).encode()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.output, "x", zipfile.ZIP_DEFLATED) as z:
        for n, b in sorted(entries.items()):
            z.writestr(n, b)
    print(a.output)


if __name__ == "__main__":
    main()
