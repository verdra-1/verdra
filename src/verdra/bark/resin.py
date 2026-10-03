# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""CA: create, rotate 30 days before expiry, Name Constraints; leaf certificates in memory.

Profiles from Master plan 10.3 (spec S-10):

- CA: subject `CN=Verdra Local CA, O=Verdra`, ECDSA P-256, valid 365 days; BasicConstraints
  CA:TRUE pathlen 0, KeyUsage keyCertSign and cRLSign, NameConstraints permitting only
  `roblox.com` and `rbxcdn.com` (all critical), SubjectKeyIdentifier.
- Leaf (one per intercepted host): subject `CN=<host>`, ECDSA P-256, valid 30 days; SAN DNS name
  = host, ExtendedKeyUsage serverAuth, AuthorityKeyIdentifier.

Nothing here touches the disk: the CA key goes to the secret store (bark/husk), leaves and their
keys stay in memory. Name Constraints follow RFC 5280 4.2.1.10: a permitted DNS name covers the
name itself and every name below it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from verdra.soil import terrain

#: Plan 10.3.
CA_VALIDITY: Final = timedelta(days=365)
CA_ROTATE_BEFORE: Final = timedelta(days=30)
LEAF_VALIDITY: Final = timedelta(days=30)
PERMITTED_DOMAINS: Final = ("roblox.com", "rbxcdn.com")
#: Certificates start this long before they are made, so a client clock a little behind the
#: system's still accepts them. The validity periods above are measured from this start.
BACKDATE: Final = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class Authority:
    """The CA certificate and its private key, in memory."""

    certificate: x509.Certificate
    key: ec.EllipticCurvePrivateKey


@dataclass(frozen=True, slots=True)
class Leaf:
    """A server certificate for one host and its private key, in memory only."""

    certificate: x509.Certificate
    key: ec.EllipticCurvePrivateKey


def new_key() -> ec.EllipticCurvePrivateKey:
    """Return a new ECDSA P-256 private key."""
    return ec.generate_private_key(ec.SECP256R1())


def create_authority(now: datetime) -> Authority:
    """Create the CA with the plan 10.3 profile, valid from `now` (minus BACKDATE)."""
    key = new_key()
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, terrain.CA_SUBJECT_COMMON_NAME),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, terrain.CA_SUBJECT_ORGANIZATION),
        ]
    )
    start = now - BACKDATE
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + CA_VALIDITY)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
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
        .add_extension(
            x509.NameConstraints(
                permitted_subtrees=[x509.DNSName(domain) for domain in PERMITTED_DOMAINS],
                excluded_subtrees=None,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return Authority(certificate, key)


def needs_rotation(certificate: x509.Certificate, now: datetime) -> bool:
    """Return whether the CA is within 30 days of expiry, or already expired."""
    return now >= certificate.not_valid_after_utc - CA_ROTATE_BEFORE


def issue_leaf(authority: Authority, host: str, now: datetime) -> Leaf:
    """Return a leaf certificate for `host` with the plan 10.3 profile, signed by the CA."""
    key = new_key()
    start = now - BACKDATE
    ski = authority.certificate.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
        .issuer_name(authority.certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + LEAF_VALIDITY)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ski.value),
            critical=False,
        )
        .sign(authority.key, hashes.SHA256())
    )
    return Leaf(certificate, key)


def certificate_pem(certificate: x509.Certificate) -> bytes:
    """Return a certificate as PEM."""
    return certificate.public_bytes(serialization.Encoding.PEM)


def trust_block(certificate: x509.Certificate) -> str:
    """Return the block Verdra adds to a Roblox trust file: its markers around the CA's PEM."""
    pem = certificate_pem(certificate).decode("ascii")
    return f"{terrain.CA_BEGIN_MARKER}\n{pem}{terrain.CA_END_MARKER}\n"


def key_to_secret(key: ec.EllipticCurvePrivateKey) -> str:
    """Return the CA key as unencrypted PKCS#8 PEM text, for the OS secret store only."""
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def key_from_secret(text: str) -> ec.EllipticCurvePrivateKey:
    """Return the CA key from its secret-store text; raise ValueError if it isn't a P-256 key."""
    key = serialization.load_pem_private_key(text.encode("ascii"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        msg = "not an ECDSA P-256 key"
        raise ValueError(msg)  # noqa: TRY004 - a wrong key is a bad value, not a bad type
    return key


def matches(certificate: x509.Certificate, key: ec.EllipticCurvePrivateKey) -> bool:
    """Return whether `key` is the private key of `certificate`."""
    return certificate.public_key() == key.public_key()


def strip_blocks(data: bytes) -> bytes:
    """Return trust-file bytes with every Verdra block removed, markers and line ends included.

    Used when a file holds a block the ledger doesn't know about, so a file never ends up with
    two (spec S-10, rule 2).
    """
    begin = terrain.CA_BEGIN_MARKER.encode("ascii")
    end = terrain.CA_END_MARKER.encode("ascii")
    while (start := data.find(begin)) != -1:
        stop = data.find(end, start)
        if stop == -1:
            break
        stop += len(end)
        if data[stop : stop + 2] == b"\r\n":
            stop += 2
        elif data[stop : stop + 1] == b"\n":
            stop += 1
        data = data[:start] + data[stop:]
    return data
