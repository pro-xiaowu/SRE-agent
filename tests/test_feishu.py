from sre_agent.channels.feishu import feishu_challenge, verify_feishu_signature


def test_url_verification():
    assert feishu_challenge({"type": "url_verification", "challenge": "abc"}) == {"challenge": "abc"}


def test_signature_roundtrip():
    import hashlib

    body = b'{"hello":1}'
    ts, nonce, key = "1", "n", "secret"
    sig = hashlib.sha256((ts + nonce + key).encode() + body).hexdigest()
    assert verify_feishu_signature(ts, nonce, key, body, sig) is True
    assert verify_feishu_signature(ts, nonce, key, body, "nope") is False
