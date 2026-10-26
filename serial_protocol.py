"""Line framing for UART; a serial read can contain partial or multiple lines."""

import re

_CARD_EVENT = re.compile(r"UID:([0-9A-Fa-f]{8})\|MODE:(IN|OUT)")


def parse_card_event(line):
    match = _CARD_EVENT.fullmatch(line.strip())
    if match is None:
        return None
    return match[1].upper(), match[2]


class SerialLineBuffer:
    def __init__(self, max_length=127):
        self.max_length = max_length
        self.buffer = bytearray()
        self.discarding = False

    def feed(self, data):
        lines = []
        for byte in data:
            if byte in (10, 13):
                if self.buffer and not self.discarding:
                    try:
                        lines.append(self.buffer.decode("ascii"))
                    except UnicodeDecodeError:
                        pass
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                if len(self.buffer) >= self.max_length:
                    self.buffer.clear()
                    self.discarding = True
                else:
                    self.buffer.append(byte)
        return lines
