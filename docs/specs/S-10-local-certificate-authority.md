# S-10 Local certificate authority

**Status:** Agreed
**Milestone:** M1
**Risk badge:** none (part of routing)
**Plan sections:** 9.4, 10.1, 10.3, 10.6, 10.8, 11.1–11.3 (trust files, confirm at M1), 15 (R-03, inactive;
R-10, R-17), Reference R3 (CA subject, markers, secret item `ca-key`), R5 (M-CA-01 to M-CA-03)

## Purpose

Create and manage the one certificate authority that lets Verdra read Roblox's traffic, trusted
only by Roblox.

## Behaviour

- **Creation.** The first time routing starts, Verdra creates the CA with exactly the properties in
  plan 10.3: subject `CN=Verdra Local CA, O=Verdra`; key ECDSA P-256 (RSA 3072 only if the M1
  check finds a Roblox client that rejects ECDSA, risk R-17, recorded in a decision record);
  validity 365 days; extensions BasicConstraints CA:TRUE pathlen 0 (critical), KeyUsage
  keyCertSign and cRLSign (critical), NameConstraints permitting only `roblox.com` and
  `rbxcdn.com` (critical), SubjectKeyIdentifier.
- **Key storage.** The private key goes to the OS secret store, service
  `io.github.verdra-1.verdra`, item `ca-key` (plan 10.6). Only the certificate is written to
  disk, as `trust/ca.crt` in the config folder.
- **Leaf certificates.** For each intercepted host, a leaf is generated in memory at startup (or
  on first use): ECDSA P-256, 30 days, SAN DNS name = host, ExtendedKeyUsage serverAuth,
  AuthorityKeyIdentifier. Leaves and their keys are never written to disk.
- **Trust files.** Verdra adds its certificate to every Roblox trust file it finds (the paths
  are the ones recorded in `docs/platforms/<os>.md` at M1; plan 11 marks them "confirm at M1").
  The certificate goes in as one block between the lines `# BEGIN Verdra Local CA` and
  `# END Verdra Local CA`. A ledger entry of kind `ca_roblox_bundle` (plan 9.4) is written
  before each file is changed (write-ahead) and marked done afterwards; it stores the file's
  path, its SHA-256 before the change and its original read-only flag.
- **New Roblox versions.** Verdra watches the Roblox install folders. When a new version folder
  appears while Verdra runs, it adds the block there too and writes M-CA-02 to Activity.
- **Rotation.** 30 days before expiry, Verdra creates a new CA, removes the old block from every
  trust file, adds the new block, then deletes the old key. At no point is more than one Verdra
  block in a file.
- **Removal.** Reset everything (S-16) removes every block and deletes the key from the secret
  store.

## Rules

1. Never add the CA to the Windows, macOS or Linux system trust stores (plan 10.3).
2. Never more than one Verdra block per trust file.
3. Trust files are edited only through `soil/atomic` (temp file, fsync, rename); a file's
   original read-only flag is restored after the edit.
4. A file without Verdra's block must be byte-identical after Verdra's block is added and
   removed again.
5. Code that touches a trust file reads its path from `docs/platforms/<os>.md` facts encoded in
   `soil/*/files.py`; no path is hard-coded before it is confirmed (plan 16.4).
6. The CA private key is never written to disk, logged, exported or put in a support bundle;
   the one exception is the Linux fallback (one file, mode 0600, M-CA-03), which Reset
   everything deletes.

## Messages

- M-CA-01 (Notice) "Verdra couldn't add its certificate to Roblox at <path>: <reason>."
- M-CA-02 (Activity) "Roblox updated. Verdra added its certificate to the new version."
- M-CA-03 (Notice, new) "Your system has no secure storage. Verdra keeps its certificate key in a
  file only your user can read."

## Acceptance tests

1. The created CA has every property and extension in plan 10.3, and a certificate for
   `example.com` signed by it fails path validation (Name Constraints), while one for
   `assetdelivery.roblox.com` passes.
2. On a copy of each recorded trust-file fixture, the block is added exactly once (adding twice
   leaves one block) and removing it leaves the file byte-identical to the original, read-only
   flag included.
3. A new Roblox version folder created while Verdra runs gets the block within 10 s and M-CA-02
   in Activity.
4. Rotation (clock moved to 30 days before expiry) leaves exactly one valid block per file, signed
   by the new CA, and the old key is gone from the secret store.
5. After creation, a scan of the config, cache, log and temp folders finds no private-key
   material (PEM, DER or raw scalar of the CA key), except the documented Linux fallback when no
   Secret Service exists: then exactly one key file, mode 0600, owned by the user, M-CA-03 shown,
   and the file deleted by Reset everything (plan S-10 test 5, as amended in 16.2).
6. Leaf certificates for each 10.2 host verify against the CA and carry the leaf profile in 10.3;
   no leaf or leaf key appears on disk.
7. Every trust-file change has a `ca_roblox_bundle` ledger entry written before the change, and a
   crash between the ledger write and the file change leaves an entry Reset everything can undo.
8. (manual, at the M1 gate) On each platform, Roblox launched through Verdra running from source
   with `--diagnose-interception` accepts a leaf signed by the CA (the request succeeds through
   the proxy and Activity shows the verified TLS details), with ECDSA, or RSA 3072 if R-17
   applied.

## Lives in

`bark/resin.py` (CA and leaves), `bark/husk.py` (secret store), `bark/scar.py` (ledger entries),
`roots/gardener.py` (adds the CA to trust files on routing start), `soil/*/files.py` (trust-file
paths per OS).

## Refinements from the plan

- Test 2 runs on fixtures of the trust files recorded at M1, so it stays automatable; the real
  files are covered by the manual test 8 and the verification protocol in `docs/platforms/`.
- Tests 6 and 7 are added: 10.3 requires leaf keys to stay in memory, and 9.4 requires
  write-ahead ledger entries; S-10 in the plan doesn't test either.
- Test 5 follows the plan's amended wording (16.2): the Linux key file is the one exception.
  The CA-key part of risk R-10 is built and tested at M1 with it; the accounts part stays at M5.
- On macOS, the trust-file edit may break the Roblox app's code signature (risk R-03). macOS is
  deferred until after 1.0 (decision record 0014) and R-03 is inactive: no macOS trust-file code
  is written and the R-03 test doesn't run. When macOS returns, the R-03 procedure in
  `docs/platforms/macos.md` runs first; if it fails, this spec changes to the fallback the plan
  names (trust bundle passed through the environment, then Hosts-file routing).
