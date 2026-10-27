#!/usr/bin/env python3
"""Build the hash-pinned DDS source inside the pinned AL2023 toolchain only."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import urllib.request


def patch_linux_resources(source):
    original = '''  FILE * fifo = popen(
    "free -k | tail -n+3 | head -n1 | awk '{print $NF}'", "r");
  int ignore = fscanf(fifo, "%llu", &kilobytesFree);
  fclose(fifo);

  ncores = sysconf(_SC_NPROCESSORS_ONLN);
  return;'''
    replacement = '''  // Lambda has no guaranteed procps tools. Bound bootstrap allocation;
  // the Python adapter further constrains resources with SetResources(32, 1).
  kilobytesFree = 256ULL * 1024ULL;
  ncores = 1;
  return;'''
    if source.count(original) != 1:
        raise ValueError("Pinned DDS Linux resource probe changed; review the patch")
    return source.replace(original, replacement)


def main():
    if sys.version_info[:2] != (3, 12) or platform.machine() != "x86_64":
        raise SystemExit("DDS staging build requires CPython 3.12 x86_64")
    release = Path("/etc/os-release").read_text()
    if 'ID="amzn"' not in release or 'VERSION_ID="2023"' not in release:
        raise SystemExit("DDS staging build requires Amazon Linux 2023")
    pins = json.loads((Path(__file__).parent / "native-source.json").read_text())
    work = Path.cwd() / "native-build"
    work.mkdir(exist_ok=True)
    archive = work / "dds-source.tar.gz"
    with urllib.request.urlopen(pins["archive"]) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != pins["sha256"]:
        raise SystemExit("DDS source archive checksum mismatch")
    archive.write_bytes(data)
    with tarfile.open(archive) as source:
        source.extractall(work, filter="data")
    root = work / ("dds-" + pins["commit"])
    system_source = root / "src" / "System.cpp"
    system_source.write_text(patch_linux_resources(system_source.read_text()))
    env = dict(os.environ, SOURCE_DATE_EPOCH="1704067200", LC_ALL="C", TZ="UTC")
    subprocess.run([
        "make", "-C", str(root / "src"), "-f", "Makefiles/Makefile_linux_shared",
        "--jobs=2", "THREADING=-DDDS_THREADS_STL", "THREAD_COMPILE=",
        "THREAD_LINK=-pthread",
        "COMPILE_FLAGS=-fPIC -O3 -std=c++11 -DDDS_THREADS_STL -pthread "
        f"-ffile-prefix-map={work}=. -fdebug-prefix-map={work}=.",
        "LINK_FLAGS=-shared -Wl,--build-id=none -Wl,-soname,libdds.so.2 "
        "-static-libstdc++ -static-libgcc -pthread",
    ], check=True, env=env)
    output = Path.cwd() / "native"
    output.mkdir(exist_ok=True)
    (output / "libdds.so.2").write_bytes((root / "src" / "libdds.so").read_bytes())
    (output / "DDS-LICENSE").write_bytes((root / "LICENSE").read_bytes())
    (output / "DDS-NOTICE").write_text(
        "DDS (Double Dummy Solver), v2.9.0\n"
        "Copyright (C) 2006-2014 Bo Haglund; 2014-2018 Bo Haglund & Soren Hein.\n"
        f"Source: {pins['repository']} at {pins['commit']}\n"
        "Distributed under Apache-2.0; see DDS-LICENSE.\n"
        "Staging modification: replaced only the Linux resource probe with a "
        "one-core / 256 MiB cap; see deployment/package/build_dds.py.\n"
    )
    print(hashlib.sha256((output / "libdds.so.2").read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
