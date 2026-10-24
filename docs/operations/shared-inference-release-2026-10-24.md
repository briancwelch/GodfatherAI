# Shared inference and worker discovery release, 2026-10-24

The owner authorized building and deploying the pending worker and Command Center
changes on 2026-10-24, lifting the prior publishing/deployment hold. The selected
release is **0.10.0-rc.3** for the coordinator and all three native installers.
Production acceptance is recorded after the build and backup-first upgrade.

This release includes the [Shared Inference wizard](shared-inference-wizard-2026-10-23.md),
managed pinned llama.cpp setup with local owner device approval and mutual TLS,
explicit local-model scanning, configurable new-node registration permissions,
the reconnect notice and native update progress/secure-connection feedback.
Worker identities, local settings and existing history are preserved. Runtime
downloads and model execution continue to require the applicable owner opt-ins.

Migration **0017_shared_engine_setup** adds durable setup and per-node consent
tables. It does not replace existing nodes, credentials or job records. Legacy
shared inference declarations remain supported.

## Validation before packaging

The source milestone passed 448 non-integration Python tests with four optional
checks skipped, the full 295-test PostgreSQL suite and a final nine-test setup
rerun including two newly added owner drain/disable cases. Dashboard components
passed 44 tests. Python/frontend lint, formatting, types and the prior dashboard
build/browser smoke passed. Native Windows fixture geometry and a wizard flow
passed. Real pinned CPU RPC discovery through mutual TLS passed; physical
multi-GPU and separate-machine inference remain hardware acceptance items.

The release preparation refreshed the native lifecycle fixture to mock the new
explicit scan and setup-refresh boundaries. Fresh and saved-identity Tk/tray
flows passed. Packaged startup now also imports the shared-engine transport and
checks its bundled pinned runtime catalog without downloading or starting an
engine.

The initial unpublished candidates found a concurrent SSL read/write timeout
on Linux and an Intel Mac dependency-build gap. The TLS bridge now uses one
nonblocking I/O owner per connection with bounded buffers and partial-write
handling. Round-trip tests include fragmented bulk transfers. Intel packaging
builds the same current cryptography release with hash-pinned Maturin/CFFI/
setuptools/Pycparser and static OpenSSL; it does not downgrade cryptography. Rc.1 and rc.2 were
not deployed.

## Release acceptance

Build, CI, installer, backup, migration, preserved-record and public TLS results
will be recorded here after verification. No contributor-host inference setup or
paid model calls are part of release activation.
