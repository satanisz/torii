"""SPEC-0002 AC-05/07 partial test: trust a supplied CA, never disable TLS."""

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
import uuid


def main() -> None:
    if sys.flags.optimize:
        raise RuntimeError("Gateway assertion tests must not run with Python optimization enabled")
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--upstream", action="store_true")
    args = parser.parse_args()
    context = ssl.create_default_context(cafile=args.ca)
    url = f"https://localhost:{args.port}"
    if args.upstream:
        request = urllib.request.Request(url + "/api/fixture")
        try:
            urllib.request.urlopen(request, context=context, timeout=5)
        except urllib.error.HTTPError as response:
            body = json.loads(response.read())
            assert response.code == 401
            assert body == {"code": "fixture_denial", "request_id": "00000000-0000-4000-8000-000000000001"}
            assert response.headers["X-Request-ID"] == body["request_id"]
        else:
            raise AssertionError("Expected upstream fixture denial")
        boundary = urllib.request.Request(url + "/api/body", data=b"x" * 262144)
        with urllib.request.urlopen(boundary, context=context, timeout=5) as response:
            assert response.status == 201
            assert json.loads(response.read()) == {"bytes": 262144}
        oversized = urllib.request.Request(url + "/api/body", data=b"x" * 262145)
        try:
            urllib.request.urlopen(oversized, context=context, timeout=5)
        except urllib.error.HTTPError as response:
            body = json.loads(response.read())
            assert response.code == 413, response.code
            assert body["code"] == "payload_too_large"
            assert body["request_id"] == response.headers["X-Request-ID"]
            assert uuid.UUID(body["request_id"]).version == 4
            assert response.headers["Content-Type"] == "application/problem+json"
            assert response.headers["Cache-Control"] == "no-store"
        else:
            raise AssertionError("Expected oversized request denial")
        print("3 gateway fixture checks PASS: upstream body/ID preservation, 262144-byte boundary, 413.")
        return
    cases = [
        (f"/auth/callback?code={args.marker}&state={args.marker}", {}, 503, "service_unavailable"),
        ("/api/v1/session", {"Host": "untrusted.invalid"}, 400, "invalid_host"),
        ("/api/v1/session", {"Host": "localhost:12345"}, 400, "invalid_host"),
    ]
    passed = 0
    ids = []
    for path, extra_headers, expected_status, code in cases:
        request = urllib.request.Request(
            url + path,
            headers={"X-Request-ID": args.marker, "Authorization": f"Bearer {args.marker}", **extra_headers},
        )
        try:
            urllib.request.urlopen(request, context=context, timeout=5)
        except urllib.error.HTTPError as response:
            body = json.loads(response.read())
            assert response.code == expected_status, response.code
            assert response.headers["Content-Type"] == "application/problem+json"
            assert response.headers["Cache-Control"] == "no-store"
            assert body["status"] == expected_status and body["code"] == code
            request_id = response.headers["X-Request-ID"]
            assert body["request_id"] == request_id
            assert uuid.UUID(request_id).version == 4
            assert request_id != args.marker
            if expected_status == 503:
                assert response.headers["Retry-After"] == "3"
            ids.append(request_id)
            passed += 1
        else:
            raise AssertionError("Expected gateway denial or unavailable upstream")
    assert len(set(ids)) == len(ids)
    print(f"{passed} gateway HTTP checks PASS (TLS verified with explicit local CA).")


if __name__ == "__main__":
    main()
