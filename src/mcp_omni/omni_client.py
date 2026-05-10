"""Native Omni gRPC client with PGP signing (no omnictl subprocess)."""

import base64
import hashlib
import json
import struct
import time
from typing import Any

import grpc
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mcp_omni.proto_gen.omni.resources import resources_pb2, resources_pb2_grpc
from mcp_omni.proto_gen.omni.management import management_pb2, management_pb2_grpc

# ─── Resource type constants ───────────────────────────────────────────────────

# Omni resources
CLUSTER_TYPE = "Clusters.omni.sidero.dev"
CLUSTER_STATUS_TYPE = "ClusterStatuses.omni.sidero.dev"
MACHINE_TYPE = "Machines.omni.sidero.dev"
MACHINE_STATUS_TYPE = "MachineStatuses.omni.sidero.dev"
MACHINE_SET_TYPE = "MachineSets.omni.sidero.dev"
MACHINE_SET_NODE_TYPE = "MachineSetNodes.omni.sidero.dev"
CLUSTER_MACHINE_TYPE = "ClusterMachines.omni.sidero.dev"
CLUSTER_MACHINE_STATUS_TYPE = "ClusterMachineStatuses.omni.sidero.dev"
CLUSTER_MACHINE_CONFIG_TYPE = "ClusterMachineConfigs.omni.sidero.dev"
TALOS_UPGRADE_STATUS_TYPE = "TalosUpgradeStatuses.omni.sidero.dev"
KUBERNETES_UPGRADE_STATUS_TYPE = "KubernetesUpgradeStatuses.omni.sidero.dev"

# Auth resources
IDENTITY_TYPE = "Identities.omni.sidero.dev"
PUBLIC_KEY_TYPE = "PublicKeys.omni.sidero.dev"
SERVICE_ACCOUNT_STATUS_TYPE = "ServiceAccountStatuses.omni.sidero.dev"
ACCESS_POLICY_TYPE = "AccessPolicies.omni.sidero.dev"
USER_TYPE = "Users.omni.sidero.dev"

# Headers included in gRPC payload signing (must match go-api-signature includedHeaders)
_SIGNED_HEADERS = [
    "x-sidero-timestamp",
    "nodes",
    "selectors",
    "fieldSelectors",
    "runtime",
    "context",
    "cluster",
    "namespace",
    "uid",
    "authorization",
]


class OmniSigner:
    """Parses a service account key and signs gRPC metadata payloads."""

    def __init__(self, sa_key_b64: str) -> None:
        sa = json.loads(base64.b64decode(sa_key_b64))
        self.identity: str = sa["name"]
        self._priv, self.fingerprint = self._parse_pgp_key(sa["pgp_key"])

    @staticmethod
    def _parse_pgp_key(armored: str) -> tuple[Ed25519PrivateKey, str]:
        body_lines = [
            l for l in armored.split("\n")
            if l and not l.startswith("---") and not l.startswith("Version")
            and not l.startswith("Comment") and not l.startswith("=")
        ]
        raw = base64.b64decode("".join(body_lines))

        # New-format packet: header byte + length byte(s) + body
        length = raw[1]
        key_body = raw[2 : 2 + length]

        # v4 EdDSA key body: version(1) + timestamp(4) + alg(1) + OID_len(1) + OID + public_MPI
        oid_len = key_body[6]
        pk_off = 7 + oid_len
        pk_bits = struct.unpack(">H", key_body[pk_off : pk_off + 2])[0]
        pk_byte_len = (pk_bits + 7) // 8
        pk_end = pk_off + 2 + pk_byte_len
        pub_body = key_body[:pk_end]

        # OpenPGP v4 fingerprint = SHA1(0x99 + 2-byte-BE-length + public_key_body)
        fp = hashlib.sha1(b"\x99" + struct.pack(">H", len(pub_body)) + pub_body).hexdigest()

        # Secret key: S2K usage (must be 0 = unprotected) + MPI
        sk_off = pk_end + 1  # skip S2K usage byte
        sk_bits = struct.unpack(">H", key_body[sk_off : sk_off + 2])[0]
        sk_byte_len = (sk_bits + 7) // 8
        priv_bytes = key_body[sk_off + 2 : sk_off + 2 + sk_byte_len]

        return Ed25519PrivateKey.from_private_bytes(priv_bytes), fp

    def _pgp_sign(self, data: bytes) -> bytes:
        """Create an OpenPGP v4 detached signature (binary format, not armored)."""
        ts = int(time.time())
        # Hashed subpacket: type 2 (creation time), 4 bytes
        hashed_sub = bytes([5, 2]) + struct.pack(">I", ts)
        # Unhashed subpacket: type 16 (issuer key ID), last 8 bytes of fingerprint
        key_id = bytes.fromhex(self.fingerprint[-16:])
        unhashed_sub = bytes([9, 16]) + key_id

        # Signature prefix (version + sig_type + pk_alg + hash_alg + hashed_sub_len + hashed_sub)
        sig_prefix = bytes([4, 0, 22, 8]) + struct.pack(">H", len(hashed_sub)) + hashed_sub
        # OpenPGP trailer: 0x04 0xFF + 4-byte length of prefix
        trailer = bytes([4, 0xFF]) + struct.pack(">I", len(sig_prefix))

        digest = hashlib.sha256(data + sig_prefix + trailer).digest()
        raw_sig = self._priv.sign(digest)  # 64 bytes: r (32) + s (32)

        def mpi(b: bytes) -> bytes:
            v = int.from_bytes(b, "big")
            bits = v.bit_length() or 1
            return struct.pack(">H", bits) + v.to_bytes((bits + 7) // 8, "big")

        sig_body = (
            sig_prefix
            + struct.pack(">H", len(unhashed_sub))
            + unhashed_sub
            + digest[:2]
            + mpi(raw_sig[:32])
            + mpi(raw_sig[32:])
        )
        n = len(sig_body)
        if n < 192:
            lb = bytes([n])
        elif n < 8384:
            lb = bytes([((n - 192) >> 8) + 192, (n - 192) & 0xFF])
        else:
            lb = bytes([0xFF]) + struct.pack(">I", n)
        return bytes([0xC2]) + lb + sig_body

    def make_metadata(self, method: str, extra: dict[str, str] | None = None) -> list[tuple[str, str]]:
        """Return signed gRPC metadata tuples for a given method."""
        ts = str(int(time.time()))

        # Build payload matching go-api-signature BuildGRPCPayload exactly:
        # - missing headers → None (marshals as null, matching Go's nil slice)
        # - Go json.Marshal sorts map keys alphabetically
        headers: dict[str, list[str] | None] = {h: None for h in _SIGNED_HEADERS}
        headers["x-sidero-timestamp"] = [ts]
        if extra:
            for k, v in extra.items():
                if k in headers:
                    headers[k] = [v]

        payload = {"headers": headers, "method": method}
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

        sig_bytes = self._pgp_sign(payload_json)
        sig_b64 = base64.b64encode(sig_bytes).decode()

        # Start with the three auth headers
        result: list[tuple[str, str]] = [
            ("x-sidero-timestamp", ts),
            ("x-sidero-payload", payload_json.decode()),
            ("x-sidero-signature", f"siderov1 {self.identity} {self.fingerprint} {sig_b64}"),
        ]
        # Also include the extra headers as actual gRPC metadata (server verifies they match payload)
        if extra:
            for k, v in extra.items():
                result.append((k, v))
        return result


class OmniClient:
    """gRPC client for the Omni API."""

    def __init__(self, endpoint: str, sa_key_b64: str) -> None:
        # Strip scheme for gRPC channel (expects host:port)
        host = endpoint.removeprefix("https://").removeprefix("http://")
        if ":" not in host:
            host = host + ":443"

        self.signer = OmniSigner(sa_key_b64)
        self._channel = grpc.secure_channel(host, grpc.ssl_channel_credentials())
        self._resources = resources_pb2_grpc.ResourceServiceStub(self._channel)
        self._management = management_pb2_grpc.ManagementServiceStub(self._channel)

    def _meta(self, method: str, runtime: str = "Omni", **extra: str) -> list[tuple[str, str]]:
        kw = {"runtime": runtime}
        kw.update(extra)
        return self.signer.make_metadata(method, kw)

    # ─── Resource API ──────────────────────────────────────────────

    def list_resources(self, resource_type: str, namespace: str = "default") -> list[dict]:
        method = "/omni.resources.ResourceService/List"
        resp = self._resources.List(
            resources_pb2.ListRequest(namespace=namespace, type=resource_type),
            metadata=self._meta(method),
        )
        return [json.loads(item) for item in resp.items]

    def get_resource(self, resource_type: str, resource_id: str, namespace: str = "default") -> dict:
        method = "/omni.resources.ResourceService/Get"
        resp = self._resources.Get(
            resources_pb2.GetRequest(namespace=namespace, type=resource_type, id=resource_id),
            metadata=self._meta(method),
        )
        return json.loads(resp.body)

    def delete_resource(self, resource_type: str, resource_id: str, namespace: str = "default") -> None:
        method = "/omni.resources.ResourceService/Delete"
        self._resources.Delete(
            resources_pb2.DeleteRequest(namespace=namespace, type=resource_type, id=resource_id),
            metadata=self._meta(method),
        )

    def create_resource(self, metadata: dict, spec: str) -> None:
        method = "/omni.resources.ResourceService/Create"
        from mcp_omni.proto_gen.v1alpha1 import resource_pb2
        meta = resource_pb2.Metadata(
            namespace=metadata.get("namespace", "default"),
            type=metadata["type"],
            id=metadata["id"],
        )
        resource = resources_pb2.Resource(metadata=meta, spec=spec)
        self._resources.Create(
            resources_pb2.CreateRequest(resource=resource),
            metadata=self._meta(method),
        )

    # ─── Management API ────────────────────────────────────────────

    def get_kubeconfig(self, cluster: str) -> bytes:
        method = "/management.ManagementService/Kubeconfig"
        resp = self._management.Kubeconfig(
            management_pb2.KubeconfigRequest(cluster=cluster)
            if hasattr(management_pb2, "KubeconfigRequest")
            else management_pb2.google_dot_protobuf_dot_empty__pb2.Empty(),
            metadata=self._meta(method, cluster=cluster),
        )
        return resp.kubeconfig

    def get_talosconfig(self, cluster: str) -> bytes:
        method = "/management.ManagementService/Talosconfig"
        resp = self._management.Talosconfig(
            management_pb2.TalosconfigRequest(),
            metadata=self._meta(method, cluster=cluster),
        )
        return resp.talosconfig

    def get_machine_logs(self, machine_id: str, tail_lines: int = 100) -> str:
        method = "/management.ManagementService/MachineLogs"
        lines = []
        for chunk in self._management.MachineLogs(
            management_pb2.MachineLogsRequest(machine_id=machine_id, tail_lines=tail_lines),
            metadata=self._meta(method),
        ):
            lines.append(chunk.SerializeToString().decode(errors="replace"))
        return "\n".join(lines)

    # ─── Convenience wrappers ──────────────────────────────────────

    def list_clusters(self) -> list[dict]:
        return self.list_resources(CLUSTER_TYPE)

    def get_cluster(self, cluster_id: str) -> dict:
        return self.get_resource(CLUSTER_TYPE, cluster_id)

    def get_cluster_status(self, cluster_id: str) -> dict:
        return self.get_resource(CLUSTER_STATUS_TYPE, cluster_id)

    def list_machines(self) -> list[dict]:
        return self.list_resources(MACHINE_TYPE)

    def get_machine_status(self, machine_id: str) -> dict:
        return self.get_resource(MACHINE_STATUS_TYPE, machine_id)

    def list_cluster_machines(self) -> list[dict]:
        return self.list_resources(CLUSTER_MACHINE_TYPE)

    # ─── Helpers ───────────────────────────────────────────────────

    def format_resources_table(self, items: list[dict]) -> str:
        if not items:
            return "(none)"
        rows = []
        for item in items:
            m = item.get("metadata", {})
            rows.append(f"{m.get('namespace','?'):<12} {m.get('type','?'):<40} {m.get('id','?'):<30} {m.get('version','?')}")
        header = f"{'NAMESPACE':<12} {'TYPE':<40} {'ID':<30} VERSION"
        return header + "\n" + "\n".join(rows)
