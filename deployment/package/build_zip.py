#!/usr/bin/env python3
"""Create a content-addressed, deterministic shared Lambda ZIP from staged inputs."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import zipfile

EPOCH = (2024, 1, 1, 0, 0, 0)
MAX_UNCOMPRESSED = 250 * 1024 * 1024
DATA_FILES = ("bridge_bidding_alg.txt", "bridge_bidding_sayc.txt")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def add_file(files, name, data):
    if name in files:
        raise ValueError(f"Package member collision: {name}")
    files[name] = data


def collect(source, dependencies, native):
    files = {}
    for path in sorted(dependencies.rglob("*")):
        relative = path.relative_to(dependencies)
        if path.is_symlink():
            raise ValueError(f"Dependency symlink is not allowed: {relative}")
        if not path.is_file() or "__pycache__" in relative.parts:
            continue
        if relative.parts[0] == "bin" or path.suffix in (".pyc", ".pyo"):
            continue
        # pip rewrites RECORD with installation-specific paths; package receipt
        # hashes every included byte instead, while retaining licenses/metadata.
        if path.name in ("RECORD", "direct_url.json"):
            continue
        add_file(files, relative.as_posix(), path.read_bytes())
    for path in sorted((source / "lambdas").rglob("*.py")):
        relative = path.relative_to(source)
        if "tests" in relative.parts or "__pycache__" in relative.parts:
            continue
        if path.name.startswith("test_") or path.is_symlink():
            continue
        add_file(files, relative.as_posix(), path.read_bytes())
    for name in DATA_FILES:
        relative = "lambdas/dds/" + name
        add_file(files, relative, (source / relative).read_bytes())
    for relative in (
        "staging_runtime.py", "deployment/runtime-routes.json",
        "deployment/package/requirements.lock", "deployment/package/native-source.json",
        "deployment/package/build_dds.py", "deployment/package/staging.Dockerfile",
    ):
        add_file(files, relative, (source / relative).read_bytes())
    library = (native / "libdds.so.2").read_bytes()
    if (len(library) < 20 or library[:5] != b"\x7fELF\x02"
            or library[5] != 1 or struct.unpack_from("<H", library, 18)[0] != 62):
        raise ValueError("DDS must be an ELF64 little-endian x86_64 shared library")
    add_file(files, "libdds.so.2", library)
    add_file(files, "DDS-LICENSE", (native / "DDS-LICENSE").read_bytes())
    add_file(files, "DDS-NOTICE", (native / "DDS-NOTICE").read_bytes())
    return files


def build(source, dependencies, native, output):
    files = collect(source, dependencies, native)
    receipt = {
        "schemaVersion": 1, "runtime": "python3.12", "architecture": "x86_64",
        "files": {name: digest(data) for name, data in sorted(files.items())},
        "note": "Build inputs only; target runtime smoke validation is a separate required gate.",
    }
    files["PACKAGE-RECEIPT.json"] = (
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    ).encode()
    if sum(map(len, files.values())) >= MAX_UNCOMPRESSED:
        raise ValueError("Lambda ZIP exceeds the 250 MiB uncompressed package limit")
    output.mkdir(parents=True, exist_ok=True)
    # The caller supplies an isolated build output directory, never a tracked ZIP.
    candidate = output / "bridge-staging-building.zip"
    with zipfile.ZipFile(candidate, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=EPOCH)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    zip_digest = digest(candidate.read_bytes())
    destination = output / f"bridge-staging-{zip_digest}.zip"
    if destination.exists():
        if destination.read_bytes() != candidate.read_bytes():
            raise ValueError("Immutable artifact name collision")
        candidate.unlink()
    else:
        candidate.rename(destination)
    metadata = {
        "artifact": destination.name, "sha256": zip_digest,
        "codeSha256": base64.b64encode(bytes.fromhex(zip_digest)).decode(),
        "uncompressedBytes": sum(map(len, files.values())),
        "memberCount": len(files), "nativeSha256": digest(files["libdds.so.2"]),
        "routeManifestSha256": digest(files["deployment/runtime-routes.json"]),
        "dependencyLockSha256": digest(files["deployment/package/requirements.lock"]),
        "nativeSourceSha256": digest(files["deployment/package/native-source.json"]),
    }
    metadata_path = output / f"bridge-staging-{zip_digest}.json"
    encoded = json.dumps(metadata, sort_keys=True, indent=2) + "\n"
    if metadata_path.exists() and metadata_path.read_text() != encoded:
        raise ValueError("Immutable artifact metadata collision")
    metadata_path.write_text(encoded)
    (output / f"bridge-staging-{zip_digest}.sha256").write_text(
        f"{zip_digest}  {destination.name}\n"
    )
    print(json.dumps(metadata, sort_keys=True))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.dependencies, args.native, args.output)


if __name__ == "__main__":
    main()
