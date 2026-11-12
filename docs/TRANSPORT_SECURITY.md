# Transport security: current limits and next steps

This is a developer note, not a claim that encrypted transport is implemented.

## Current behavior

Pairing uses a temporary TLS listener and a certificate fingerprint carried in the one-time pairing link. Device owners compare a code and approve the connection. Discovery authenticates responses with HMAC.

The normal PC API, uploads and desktop stream still use HTTP. The phone mirror uses a plain framed TCP socket. These channels need transport encryption; pairing and HMAC discovery do not provide it. Use only trusted LANs. Do not expose the listeners to the Internet.

## A compatible migration requires both applications

1. Persist the approved PC certificate identity on Android and use a scoped pinned HTTPS client for every API call, upload and desktop stream. Never disable certificate verification globally.
2. Serve HTTPS with a stable local identity, separate from short-lived pairing sessions; decide how pairing delivers the operational identity and how deliberate identity rotation is approved.
3. Give the Android mirror a stable TLS identity and securely bind its fingerprint to the approved pairing. The Windows viewer must verify it before transmitting credentials or control events.
4. Version the pairing protocol and discovery capability metadata. Existing installations must show an explicit upgrade/re-pairing message, not silently fall back to plaintext after a TLS error.
5. Test new installs, upgrades, changing LAN addresses, unknown/replaced certificates, revoked pairings, interrupted uploads, both video directions and consent/session invalidation on real devices.

Transport encryption does not remove platform permissions, make arbitrary downloaded executables safe, or replace authentication and input validation. Until this migration is implemented and checked, documentation must keep the trusted-LAN warning.
