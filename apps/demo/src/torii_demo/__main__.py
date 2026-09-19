"""Explicit local-only process entry point, SPEC-0018 D06/D07."""

import argparse
import socket
from pathlib import Path

import uvicorn

from torii_demo.app import create_app


def main():
    parser = argparse.ArgumentParser(description="Torii local concept demo — not for company data")
    parser.add_argument("--local-demo", action="store_true", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    # Claim the fixed loopback endpoint before opening/recovering persistent state.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 18440))
        app = create_app(args.data_dir)
        server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=18440, workers=1, access_log=False, log_level="warning"
            )
        )
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
