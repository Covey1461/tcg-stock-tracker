# Security

## Secrets and credentials

TCG Resale Evaluator must not store API keys, passwords, OAuth tokens, private keys, or service-account credentials in source control. Future API integrations must read secrets from environment variables or the operating system credential store.

Local `.env` files and common credential/key formats are ignored by Git. A repository secret scan runs in CI.

If a credential is ever committed, treat it as compromised: revoke/rotate it first, then remove it from Git history. Deleting it in a later commit is not sufficient.

## Security checks

Pull requests run:

- unit tests
- a repository secret-pattern scan
- Bandit static analysis for Python security issues
- pip-audit against Python dependency advisories

GitHub Actions dependencies are pinned to full commit SHAs and CI uses read-only repository permissions.

## Local file safety

The app only accepts a phone trigger named `process` (case-insensitive, any extension) when the trigger is a real file directly inside the configured app root. Trigger paths outside that root are rejected. Generated lot IDs are restricted to a safe filename character set to prevent path traversal.

Because the app processes marketplace images, Pillow is constrained to 12.3.0 or newer within the 12.x line to include current 2026 image-parser security fixes.

## Reporting

Do not put real credentials or personal data in a public GitHub issue. If a security issue involves an exposed secret, rotate the secret before discussing remediation.
