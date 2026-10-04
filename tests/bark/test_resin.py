# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-10: the CA and leaf certificates (Master plan 10.3)."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError

from verdra.bark import resin
from verdra.soil import terrain

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
#: Plan 10.2: the hosts Verdra may intercept, and a CDN host under rbxcdn.com.
HOSTS = (
    "assetdelivery.roblox.com",
    "clientsettings.roblox.com",
    "clientsettingscdn.roblox.com",
    "gamejoin.roblox.com",
    "apis.roblox.com",
    "fts.rbxcdn.com",
)


@pytest.fixture(scope="module")
def authority() -> resin.Authority:
    return resin.create_authority(NOW)


def verify(authority: resin.Authority, leaf: resin.Leaf, host: str) -> None:
    verifier = (
        PolicyBuilder()
        .store(Store([authority.certificate]))
        .time(NOW)
        .build_server_verifier(x509.DNSName(host))
    )
    verifier.verify(leaf.certificate, [])


def extension[T: x509.ExtensionType](cert: x509.Certificate, kind: type[T]) -> x509.Extension[T]:
    return cert.extensions.get_extension_for_class(kind)


@pytest.mark.spec("S-10", 1)
def test_the_ca_has_the_plan_profile(authority: resin.Authority) -> None:
    cert = authority.certificate
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "Verdra Local CA"
    assert cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == "Verdra"
    assert cert.issuer == cert.subject
    assert isinstance(authority.key, ec.EllipticCurvePrivateKey)
    assert isinstance(authority.key.curve, ec.SECP256R1)
    assert cert.not_valid_after_utc - cert.not_valid_before_utc == timedelta(days=365)
    assert cert.not_valid_before_utc <= NOW
    basic = extension(cert, x509.BasicConstraints)
    assert basic.critical and basic.value.ca and basic.value.path_length == 0
    usage = extension(cert, x509.KeyUsage)
    assert usage.critical and usage.value.key_cert_sign and usage.value.crl_sign
    assert not usage.value.digital_signature
    names = extension(cert, x509.NameConstraints)
    assert names.critical
    assert names.value.permitted_subtrees == [
        x509.DNSName("roblox.com"),
        x509.DNSName("rbxcdn.com"),
    ]
    assert names.value.excluded_subtrees is None
    ski = extension(cert, x509.SubjectKeyIdentifier)
    assert ski.value == x509.SubjectKeyIdentifier.from_public_key(authority.key.public_key())
    assert {e.oid for e in cert.extensions} == {
        x509.BasicConstraints.oid,
        x509.KeyUsage.oid,
        x509.NameConstraints.oid,
        x509.SubjectKeyIdentifier.oid,
    }
    assert resin.matches(cert, authority.key)


@pytest.mark.spec("S-10", 1)
def test_name_constraints_allow_only_roblox_hosts(authority: resin.Authority) -> None:
    verify(
        authority,
        resin.issue_leaf(authority, "assetdelivery.roblox.com", NOW),
        "assetdelivery.roblox.com",
    )
    for host in ("example.com", "roblox.com.example.com", "notroblox.com"):
        leaf = resin.issue_leaf(authority, host, NOW)
        with pytest.raises(VerificationError):
            verify(authority, leaf, host)


@pytest.mark.spec("S-10", 6)
@pytest.mark.parametrize("host", HOSTS)
def test_leaves_carry_the_leaf_profile_and_verify(authority: resin.Authority, host: str) -> None:
    leaf = resin.issue_leaf(authority, host, NOW)
    cert = leaf.certificate
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == host
    assert cert.issuer == authority.certificate.subject
    assert isinstance(leaf.key.curve, ec.SECP256R1)
    assert cert.not_valid_after_utc - cert.not_valid_before_utc == timedelta(days=30)
    assert extension(cert, x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == [
        host
    ]
    assert list(extension(cert, x509.ExtendedKeyUsage).value) == [ExtendedKeyUsageOID.SERVER_AUTH]
    aki = extension(cert, x509.AuthorityKeyIdentifier).value
    ski = extension(authority.certificate, x509.SubjectKeyIdentifier).value
    assert aki.key_identifier == ski.digest
    assert {e.oid for e in cert.extensions} == {
        x509.SubjectAlternativeName.oid,
        x509.ExtendedKeyUsage.oid,
        x509.AuthorityKeyIdentifier.oid,
    }
    verify(authority, leaf, host)
    # A leaf for one host doesn't verify for another.
    with pytest.raises(VerificationError):
        verify(authority, leaf, "other.roblox.com")


def test_each_leaf_has_its_own_key(authority: resin.Authority) -> None:
    first = resin.issue_leaf(authority, "apis.roblox.com", NOW)
    second = resin.issue_leaf(authority, "apis.roblox.com", NOW)
    assert first.key.public_key() != second.key.public_key()
    assert first.certificate.serial_number != second.certificate.serial_number


def test_rotation_starts_30_days_before_expiry(authority: resin.Authority) -> None:
    expiry = authority.certificate.not_valid_after_utc
    assert not resin.needs_rotation(authority.certificate, NOW)
    assert not resin.needs_rotation(authority.certificate, expiry - timedelta(days=30, seconds=1))
    assert resin.needs_rotation(authority.certificate, expiry - timedelta(days=30))
    assert resin.needs_rotation(authority.certificate, expiry + timedelta(days=1))


def test_the_trust_block_is_the_pem_between_the_markers(authority: resin.Authority) -> None:
    block = resin.trust_block(authority.certificate)
    lines = block.splitlines()
    assert lines[0] == terrain.CA_BEGIN_MARKER
    assert lines[-1] == terrain.CA_END_MARKER
    assert block.endswith("\n")
    pem = "\n".join(lines[1:-1]) + "\n"
    assert x509.load_pem_x509_certificate(pem.encode()) == authority.certificate


def test_the_key_round_trips_through_its_secret_text(authority: resin.Authority) -> None:
    text = resin.key_to_secret(authority.key)
    assert text.startswith("-----BEGIN PRIVATE KEY-----")
    assert resin.matches(authority.certificate, resin.key_from_secret(text))
    other = resin.create_authority(NOW)
    assert not resin.matches(authority.certificate, other.key)


def test_a_key_that_isnt_p256_is_refused() -> None:
    p384 = ec.generate_private_key(ec.SECP384R1())
    with pytest.raises(ValueError, match="P-256"):
        resin.key_from_secret(resin.key_to_secret(p384))
    with pytest.raises(ValueError):
        resin.key_from_secret("not a key")
