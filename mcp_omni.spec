# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for mcp-omni standalone binary."""

import sys
from pathlib import Path

src = Path("src")

a = Analysis(
    ["src/mcp_omni/server.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("src/mcp_omni/proto_gen", "mcp_omni/proto_gen"),
    ],
    hiddenimports=[
        # gRPC internals
        "grpc",
        "grpc._channel",
        "grpc._server",
        "grpc._interceptor",
        "grpc.experimental",
        # Protobuf
        "google.protobuf",
        "google.protobuf.descriptor",
        "google.protobuf.descriptor_pool",
        "google.protobuf.message_factory",
        "google.protobuf.reflection",
        "google.protobuf.symbol_database",
        "google.protobuf.internal.containers",
        "google.protobuf.runtime_version",
        # Cryptography
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.backends.openssl",
        # MCP
        "mcp",
        "mcp.server",
        "mcp.server.stdio",
        "mcp.types",
        "anyio",
        "anyio._backends._asyncio",
        "anyio.streams.memory",
        # Proto generated stubs
        "mcp_omni.proto_gen",
        "mcp_omni.proto_gen.omni",
        "mcp_omni.proto_gen.omni.resources",
        "mcp_omni.proto_gen.omni.management",
        "mcp_omni.proto_gen.common",
        "mcp_omni.proto_gen.v1alpha1",
        "mcp_omni.proto_gen.google",
        "mcp_omni.proto_gen.google.rpc",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mcp-omni",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
