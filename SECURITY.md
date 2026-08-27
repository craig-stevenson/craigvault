# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue. Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository ("Security" tab → "Report a vulnerability").

Include what you can: affected browser and version, reproduction steps, and the impact you believe the issue has. Expect an initial response within a week or so — this is a hobby project maintained in spare time, so please be patient.

## Scope

In scope: flaws in the encryption, key derivation, file format, or lock/unlock logic that could expose plaintext or weaken the password boundary. That explicitly includes the hand-written scrypt core (Salsa20/8, BlockMix, ROMix) and the versioned `SECTXT2` header — in particular anything that would let stored KDF parameters be downgraded, or a `SECTXT1` file be processed on the wrong path.

Out of scope (documented limits, not bugs — see the security notes in the README):

- Plaintext or password remaining in browser memory while a document is unlocked. Locking discards the key and clears every password field, so this covers the unlocked state; a *locked* session that still exposes the key or the plaintext is in scope.
- OS-level attacks such as memory dumps, swap files, or keyloggers
- Weak user-chosen passwords
- The `SECTXT2` header, and the HTML shell around it, identifying a file as a CraigVault vault
- The ~0.25s unlock delay: it is the cost that makes offline guessing expensive, and is meant to be felt
- The app and the encrypted document living in one file: opening a vault runs the editor stored inside it, so treat an untrusted vault as you would any untrusted HTML

## Supported versions

Only the latest commit on `main` is supported.
