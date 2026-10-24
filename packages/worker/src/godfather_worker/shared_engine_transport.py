"""Per-group mutual TLS around loopback-only native RPC. No public raw RPC listener."""

import hashlib
import hmac
import socket
import ssl
import threading
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def hostname(node_id: UUID, group_id: UUID) -> str:
    return f"{node_id.hex}.{group_id.hex}.shared.godfather.invalid"


def identity(folder: Path, node_id: UUID, group_id: UUID) -> tuple[Path, Path, str]:
    root = folder / "shared-engine/identities" / group_id.hex
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    certificate, private = root / "certificate.pem", root / "private.pem"
    if certificate.exists() and private.exists():
        return certificate, private, certificate.read_text(encoding="ascii")
    if certificate.exists() or private.exists():
        raise ValueError("The local group identity is incomplete; repair it before approving")
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Godfather shared inference")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname(node_id, group_id))]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    with private.open("xb") as output:
        output.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    private.chmod(0o600)
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    certificate.chmod(0o600)
    return certificate, private, certificate.read_text(encoding="ascii")


def contexts(
    folder: Path, node_id: UUID, group_id: UUID, peer_pem: str, server: bool
) -> ssl.SSLContext:
    certificate, private, _ = identity(folder, node_id, group_id)
    context = (
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if server
        else ssl.create_default_context(cadata=peer_pem)
    )
    if server:
        context.load_verify_locations(cadata=peer_pem)
        context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(certificate), str(private))
    return context


def fingerprint(pem: str) -> bytes:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).digest()


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class Bridge:
    """One fixed target, a bounded connection count, and exact peer certificate pinning."""

    def __init__(
        self,
        host: str,
        port: int,
        target: tuple[str, int],
        context: ssl.SSLContext,
        peer_pem: str,
        *,
        server: bool,
        peer_name: str | None = None,
    ) -> None:
        self.target, self.context, self.server, self.peer_name = target, context, server, peer_name
        self.expected = fingerprint(peer_pem)
        self.stop_event = threading.Event()
        self.guard = threading.Lock()
        self.slots = threading.BoundedSemaphore(8)
        self.connections: set[socket.socket] = set()
        self.workers: set[threading.Thread] = set()
        self.listener = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET)
        self.listener.settimeout(0.5)
        self.listener.bind((host, port))
        self.listener.listen(8)
        self.port = int(self.listener.getsockname()[1])
        self.thread = threading.Thread(target=self.accept, daemon=True)
        self.thread.start()

    def accept(self) -> None:
        while not self.stop_event.is_set():
            try:
                incoming, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            if not self.slots.acquire(blocking=False):
                incoming.close()
                continue
            worker = threading.Thread(target=self.forward, args=(incoming,), daemon=True)
            with self.guard:
                self.workers.add(worker)
            worker.start()

    def forward(self, incoming: socket.socket) -> None:
        sockets: list[socket.socket] = [incoming]
        finished = threading.Event()
        try:
            incoming.settimeout(5)
            if self.server:
                incoming = self.context.wrap_socket(incoming, server_side=True)
                sockets.append(incoming)
                secured = incoming
            else:
                secured = self.context.wrap_socket(
                    socket.create_connection(self.target, timeout=5), server_hostname=self.peer_name
                )
                sockets.append(secured)
            actual = hashlib.sha256(secured.getpeercert(binary_form=True) or b"").digest()
            if not hmac.compare_digest(actual, self.expected):
                raise ssl.SSLError("Peer certificate changed")
            other = socket.create_connection(self.target, timeout=5) if self.server else secured
            if self.server:
                sockets.append(other)
            with self.guard:
                self.connections.update(sockets)

            def copy(source: socket.socket, destination: socket.socket) -> None:
                try:
                    while not self.stop_event.is_set() and not finished.is_set():
                        try:
                            data = source.recv(65536)
                        except TimeoutError:
                            continue
                        if not data:
                            return
                        destination.sendall(data)
                except OSError:
                    pass
                finally:
                    finished.set()

            incoming.settimeout(1)
            other.settimeout(1)
            reverse = threading.Thread(target=copy, args=(other, incoming), daemon=True)
            reverse.start()
            copy(incoming, other)
            for connection in sockets:
                with suppress(OSError):
                    connection.shutdown(socket.SHUT_RDWR)
            reverse.join(2)
        except OSError:
            pass
        finally:
            for connection in sockets:
                connection.close()
            with self.guard:
                self.connections.difference_update(sockets)
                self.workers.discard(threading.current_thread())
            self.slots.release()

    def close(self) -> None:
        self.stop_event.set()
        self.listener.close()
        with self.guard:
            connections, workers = list(self.connections), list(self.workers)
        for connection in connections:
            with suppress(OSError):
                connection.shutdown(socket.SHUT_RDWR)
        self.thread.join(2)
        for worker in workers:
            worker.join(2)
