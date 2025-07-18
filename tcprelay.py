import sys
import socket
import select
import threading
import argparse
from usbmux import USBMux, MuxDevice

class TCPRelay:
    def __init__(self, remote_port, local_port, device: MuxDevice):
        self.local_port = local_port
        self.remote_port = remote_port
        self.device = device
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('localhost', self.local_port))
        self.server.listen(5)
        print(f"[+] Listening on localhost:{self.local_port}, forwarding to device port {self.remote_port}")

    def handle_connection(self, client_sock):
        try:
            mux = USBMux()
            if not mux.devices:
                mux.process(1.0)  # 等待设备
            device = mux.devices[0]
            device_sock = mux.connect(device, self.remote_port)  # 连接设备目标端口
            # device_sock = self.device.connect_tcp(self.remote_port)
        except Exception as e:
            print(f"[-] Could not connect to device port {self.remote_port}: {e}")
            client_sock.close()
            return

        def forward(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                src.close()
                dst.close()

        threading.Thread(target=forward, args=(client_sock, device_sock)).start()
        threading.Thread(target=forward, args=(device_sock, client_sock)).start()

    def serve_forever(self):
        try:
            while True:
                client_sock, _ = self.server.accept()
                threading.Thread(target=self.handle_connection, args=(client_sock,)).start()
        except KeyboardInterrupt:
            print("\n[!] Shutting down server")
            self.server.close()


def parse_ports(ports):
    port_pairs = []
    for pair in ports:
        if ':' in pair:
            local, remote = map(int, pair.split(':'))
        else:
            local = remote = int(pair)
        port_pairs.append((local, remote))
    return port_pairs


def main():
    parser = argparse.ArgumentParser(description='TCP port forwarding over USB using usbmuxd')
    parser.add_argument('ports', nargs='+', help='Port(s) to forward [local:remote or port]')
    parser.add_argument('-t', '--first', action='store_true', help='Use first connected device')
    args = parser.parse_args()

    mux = USBMux()
    mux.process(1.0)

    if not mux.devices:
        print("[-] No device found")
        return

    device = mux.devices[0] if args.first else mux.devices[-1]
    print(f"[+] Using device: UDID={device.devid} Serial={device.serial}")

    port_pairs = parse_ports(args.ports)
    relays = [TCPRelay(local, remote, device) for local, remote in port_pairs]

    for relay in relays:
        threading.Thread(target=relay.serve_forever, daemon=True).start()

    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        print("\n[!] Exiting")


if __name__ == '__main__':
    main()
