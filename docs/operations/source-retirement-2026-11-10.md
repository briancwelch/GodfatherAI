# Source preservation and local retirement - November 10, 2026

The owner marked The Godfather inactive and authorized credential cleanup,
an end-user README and a source push to the existing GitHub repository. The owner
also explicitly authorized erasing this computer's Godfather database, worker
sign-ins and local runtime data. This work does not authorize a new release or
retirement of a hosted installation.

## Source changes

- Rewrote the main README around what the product does, what users need,
  connecting a computer, choosing a model, running a job and troubleshooting.
- Marked the README and documentation index inactive. Historical hostnames and
  release reports do not establish current service or download availability.
- Expanded Git exclusions for environment backups, credential files, worker/admin
  identity files, browser authentication state and infrastructure state files.
  Empty/example configuration templates remain tracked.
- Preserved application source, synthetic test fixtures and existing release
  installers. No worker installers were rebuilt or published.

## Local data removed

- The checkout's populated `.env` and `.cache` tree, including historical production
  OAuth configuration copies, generated worker/admin tokens, database backups,
  browser test profiles, shared-inference private keys and local execution artifacts.
- Python tool caches and the generated dashboard build.
- The local OAuth configuration-reference folder under `dist`.
- The Godfather worker's Windows Credential Manager entry and its local application
  data folder, including both desktop and earlier worker configurations.
- Docker volumes `godfather-local_postgres-data` and
  `godfather-local_artifacts-data`, after verifying their Compose project labels.
  No Godfather containers remained at final verification.

No credential-bearing backup was made of the data the owner requested to erase.
Other projects' containers and volumes were preserved. No persistent Godfather or
Consigliere environment variables were found in the current Windows user's or
machine's environment. Final Windows credential enumeration found no Godfather or
Consigliere entries.

Retained `dist` release environment files contain only the five packaged Docker
image references; they contain no account settings or credentials. Those packages
remain ignored by Git.

## Checks actually performed

- Scanned 463 tracked files and the pre-existing reachable Git history of 120
  commits / 1,455 unique blobs for private keys, common provider/GitHub/AWS token
  formats, OAuth secrets, JWTs, credential-bearing URLs and known saved environment
  secrets. No matches were found. Credential-like literal assignments in tracked
  files were confined to synthetic tests; the rejected `never-accepted` value is
  an input-validation fixture.
- Scanned ignored cache/distribution text files before cleanup and rescanned
  retained distribution text files afterward. No credential-pattern matches
  remained. This pattern scan is not proof that an arbitrary unknown secret cannot
  exist, and it did not inspect every byte of packaged binaries or image archives.
- Verified that all eight targeted local paths were absent, no Godfather Docker
  containers or volumes remained, and no project Windows credentials or persistent
  project environment variables remained.
- Verified 13 sensitive filename examples are ignored and both tracked environment
  templates remain available.
- Checked all 41 relative links in the two README files.
- Ran `python -m pytest tests/test_release.py -q -p no:cacheprovider`:
  **11 passed**. These include the packaging test that excludes operator secrets.
- Ran Prettier checks for the changed Markdown and `git diff --check`: passed.
- Read GitHub repository settings: the repository remains private, with no saved
  Actions secrets, Actions variables or deployment environments.

The changes affect documentation and Git exclusions. Application builds,
database integration tests, signed-in browser flows and physical worker/inference
tests were not rerun. Local services were not restarted after retirement.

## Remaining boundaries

Deleting local credentials does not revoke them at Google, an AI provider or a
hosted coordinator. Hosted databases, sessions, credentials, DNS and services were
not accessed or changed. Other computers and browser profiles outside this
checkout were not cleaned. Account-wide GitHub authentication remains available
for the explicitly requested source push.

Any later hosted shutdown or provider-key revocation requires its own explicit
scope. No further implementation milestone was started.
