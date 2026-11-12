"""Authenticated LAN discovery. UDP never carries the pairing key.

Wire format (ASCII, HMAC-SHA256 lowercase hex over everything before last '|'):
PCMOTE_DISCOVERY|1|request|<32 lowercase hex nonce>|<hmac>
PCMOTE_DISCOVERY|1|response|<nonce>|<HTTP port>|<MAC>|<broadcast>|<hmac>
The receiver uses the datagram source IP, not an advertised host field.
"""
import ctypes
import hashlib
import hmac
import ipaddress
import os
import re
import socket
import threading
import time

PREFIX = 'PCMOTE_DISCOVERY|1|'
NONCE = re.compile(r'^[0-9a-f]{32}$')
MAC = re.compile(r'^[0-9A-F]{2}(?:-[0-9A-F]{2}){5}$')
MAX_PACKET = 512


def _sign(body, key):
    if not key:
        raise ValueError('Discovery requires a configured key')
    return (body + '|' + hmac.new(key.encode('utf-8'), body.encode('ascii'), hashlib.sha256).hexdigest()).encode('ascii')


def _verify(packet, key, kind, count):
    if not key or not packet or len(packet) > MAX_PACKET:
        return None
    try:
        text = packet.decode('ascii')
        parts = text.split('|')
        if len(parts) != count or parts[:3] != ['PCMOTE_DISCOVERY', '1', kind] or not NONCE.fullmatch(parts[3]):
            return None
        body, signature = text.rsplit('|', 1)
        expected = hmac.new(key.encode('utf-8'), body.encode('ascii'), hashlib.sha256).hexdigest()
        return parts if hmac.compare_digest(signature, expected) else None
    except (ValueError, UnicodeError, IndexError):
        return None


def make_request(key, nonce):
    if not NONCE.fullmatch(nonce):
        raise ValueError('Invalid nonce')
    return _sign(PREFIX + 'request|' + nonce, key)


def verify_request(packet, key):
    parts = _verify(packet, key, 'request', 5)
    return parts[3] if parts else None


def make_response(key, nonce, port, adapter):
    if not NONCE.fullmatch(nonce) or not 1 <= port <= 65535 or not MAC.fullmatch(adapter.mac):
        raise ValueError('Invalid discovery response')
    return _sign(PREFIX + 'response|%s|%d|%s|%s' % (nonce, port, adapter.mac, adapter.broadcast), key)


def verify_response(packet, key, nonce):
    parts = _verify(packet, key, 'response', 8)
    if not parts or parts[3] != nonce or not MAC.fullmatch(parts[5]):
        return None
    try:
        port = int(parts[4])
        address = ipaddress.IPv4Address(parts[6])
        if not 1 <= port <= 65535 or str(address) != parts[6]:
            return None
        return port, parts[5], parts[6]
    except ValueError:
        return None


class Adapter:
    def __init__(self, ip, mask, mac):
        self.ip = str(ipaddress.IPv4Address(ip))
        self.network = ipaddress.IPv4Network('%s/%s' % (ip, mask), strict=False)
        self.broadcast = str(self.network.broadcast_address)
        self.mac = mac.upper().replace(':', '-')


def select_adapter(adapters, local_ip, peer_ip):
    peer = ipaddress.IPv4Address(peer_ip)
    return next((a for a in adapters if a.ip == local_ip and peer in a.network and MAC.fullmatch(a.mac)), None)


def route_ip(peer):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((peer, 9))
        return probe.getsockname()[0]


def windows_adapters():
    """IP Helper GetAdaptersInfo: each IPv4 address, its mask and SAME adapter MAC."""
    if os.name != 'nt':
        return []
    # Windows ULONG is always 32-bit; time_t in this structure is pointer-sized.
    DWORD = ctypes.c_uint32
    class IP_ADDR_STRING(ctypes.Structure):
        pass
    IP_ADDR_STRING._fields_ = [('Next', ctypes.POINTER(IP_ADDR_STRING)), ('IpAddress', ctypes.c_char * 16),
                               ('IpMask', ctypes.c_char * 16), ('Context', DWORD)]
    class IP_ADAPTER_INFO(ctypes.Structure):
        pass
    IP_ADAPTER_INFO._fields_ = [
        ('Next', ctypes.POINTER(IP_ADAPTER_INFO)), ('ComboIndex', DWORD),
        ('AdapterName', ctypes.c_char * 260), ('Description', ctypes.c_char * 132),
        ('AddressLength', DWORD), ('Address', ctypes.c_ubyte * 8), ('Index', DWORD),
        ('Type', DWORD), ('DhcpEnabled', DWORD), ('CurrentIpAddress', ctypes.POINTER(IP_ADDR_STRING)),
        ('IpAddressList', IP_ADDR_STRING), ('GatewayList', IP_ADDR_STRING),
        ('DhcpServer', IP_ADDR_STRING), ('HaveWins', ctypes.c_int),
        ('PrimaryWinsServer', IP_ADDR_STRING), ('SecondaryWinsServer', IP_ADDR_STRING),
        ('LeaseObtained', ctypes.c_ssize_t), ('LeaseExpires', ctypes.c_ssize_t)]
    api = ctypes.WinDLL('iphlpapi').GetAdaptersInfo
    api.argtypes = [ctypes.c_void_p, ctypes.POINTER(DWORD)]
    api.restype = DWORD
    size = DWORD(0)
    if api(None, ctypes.byref(size)) != 111 or size.value > 1024 * 1024:
        return []
    buffer = ctypes.create_string_buffer(size.value)
    if api(buffer, ctypes.byref(size)) != 0:
        return []
    result = []
    current = ctypes.cast(buffer, ctypes.POINTER(IP_ADAPTER_INFO))
    while current:
        adapter = current.contents
        # Ethernet / WiFi only, not tunnels, loopback or point-to-point links.
        if adapter.AddressLength == 6 and adapter.Type in (6, 71):
            mac = '-'.join('%02X' % n for n in adapter.Address[:6])
            address = ctypes.pointer(adapter.IpAddressList)
            while address:
                entry = address.contents
                try:
                    ip = entry.IpAddress.decode('ascii')
                    mask = entry.IpMask.decode('ascii')
                    if ip != '0.0.0.0':
                        result.append(Adapter(ip, mask, mac))
                except (ValueError, UnicodeError):
                    pass
                address = entry.Next
        current = adapter.Next
    return result


class RateLimiter:
    def __init__(self, interval=1.0, maximum=256):
        self.interval, self.maximum = interval, maximum
        self.seen = {}

    def allow(self, source, now):
        previous = self.seen.get(source)
        if previous is not None and now - previous < self.interval:
            return False
        if source not in self.seen and len(self.seen) >= self.maximum:
            oldest = min(self.seen, key=self.seen.get)
            del self.seen[oldest]
        self.seen[source] = now
        return True


class DiscoveryServer:
    def __init__(self, key, http_port, host='0.0.0.0', port=8766,
                 adapters=windows_adapters, route=route_ip):
        if not key:
            raise ValueError('Discovery requires a configured key')
        self.key, self.http_port = key, http_port
        self.adapters, self.route = adapters, route
        self.stopped = threading.Event()
        self.limiter = RateLimiter()
        self.global_window, self.global_count = 0.0, 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind((host, port))
            self.sock.settimeout(0.25)
        except Exception:
            self.sock.close()
            raise
        self.address = self.sock.getsockname()
        self.adapter_cache = (0.0, [])

    def serve_forever(self):
        try:
            while not self.stopped.is_set():
                try:
                    packet, peer = self.sock.recvfrom(MAX_PACKET + 1)
                    now = time.monotonic()
                    if now - self.global_window >= 1:
                        self.global_window, self.global_count = now, 0
                    self.global_count += 1
                    if self.global_count > 32:
                        continue
                    nonce = verify_request(packet, self.key)
                    if nonce is None or not self.limiter.allow(peer[0], now):
                        continue
                    cached_at, adapters = self.adapter_cache
                    if now - cached_at > 5:
                        adapters = self.adapters()
                        self.adapter_cache = (now, adapters)
                    local_ip = self.route(peer[0])
                    adapter = select_adapter(adapters, local_ip, peer[0])
                    if adapter is None:
                        continue
                    response = make_response(self.key, nonce, self.http_port, adapter)
                    # Binding the reply explicitly ensures advertised MAC and source interface agree.
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reply:
                        reply.settimeout(0.25)
                        reply.bind((adapter.ip, 0))
                        reply.sendto(response, peer)
                except socket.timeout:
                    continue
                except (OSError, ValueError):
                    if self.stopped.is_set():
                        break
        finally:
            self.sock.close()

    def close(self):
        self.stopped.set()
