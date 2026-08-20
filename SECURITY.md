# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue. Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository ("Security" tab → "Report a vulnerability").

Include what you can: affected browser and version, reproduction steps, and the impact you believe the issue has. Expect an initial response within a week or so — this is a hobby project maintained in spare time, so please be patient.

## Scope

In scope: flaws in the encryption, key derivation, file format, or lock/unlock logic that could expose plaintext or weaken the password boundary.

Out of scope (documented limits, not bugs — see the security notes in the README):

- Plaintext or password remaining in browser memory while a document is unlocked
- OS-level attacks such as memory dumps, swap files, or keyloggers
- Weak user-chosen passwords
- The `SECTXT1` header identifying a file as encrypted

## Supported versions

Only the latest commit on `main` is supported.
