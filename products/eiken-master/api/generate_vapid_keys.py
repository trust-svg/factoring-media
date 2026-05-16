#!/usr/bin/env python3
"""One-time VAPID key generation. Run once and paste output into .env."""

from py_vapid import Vapid

vapid = Vapid()
vapid.generate_keys()

private_key = vapid.private_pem().decode()
public_key = vapid.public_key.public_bytes(
    encoding=__import__(
        "cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]
    ).Encoding.X962,
    format=__import__(
        "cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]
    ).PublicFormat.UncompressedPoint,
)

import base64

public_key_b64 = base64.urlsafe_b64encode(public_key).rstrip(b"=").decode()

print("Add to .env:")
print(f'VAPID_PRIVATE_KEY="{private_key.strip()}"')
print(f'VAPID_PUBLIC_KEY="{public_key_b64}"')
print('VAPID_CLAIMS_EMAIL="your-email@example.com"')
