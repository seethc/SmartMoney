"""Temporary LAN download of one source-only package; never serves the workspace."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=8876)
    parser.add_argument('--minutes', type=int, default=30)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.host)
    if not address.is_private or address.is_unspecified or address.is_multicast or address.version != 4:
        parser.error('Choose the laptop’s specific private IPv4 address.')
    if not 1 <= args.minutes <= 60:
        parser.error('Duration must be between 1 and 60 minutes.')
    payload = (Path(__file__).resolve().parent.parent / 'dist' / 'smartmoney-rpi.tar.gz').read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def do_GET(self):
            if self.path != '/smartmoney-rpi.tar.gz':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/gzip')
            self.send_header('Content-Disposition', 'attachment; filename="smartmoney-rpi.tar.gz"')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *values):
            pass

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.timeout = 1
    print(f'Package: http://{args.host}:{args.port}/smartmoney-rpi.tar.gz', flush=True)
    print(f'SHA256: {checksum}', flush=True)
    print(f'Only this package is served; expires after {args.minutes} minutes.', flush=True)
    deadline = time.monotonic() + args.minutes * 60
    try:
        while time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
