import unittest

from serial_protocol import SerialLineBuffer, parse_card_event


class SerialProtocolTests(unittest.TestCase):
    def test_fragmented_and_batched_uart_lines(self):
        buffer = SerialLineBuffer()
        self.assertEqual(buffer.feed(b"UID:aabb"), [])
        self.assertEqual(
            buffer.feed(b"ccdd|MODE:IN\r\nMODE:OUT\nUID:01020304|MODE:"),
            ["UID:aabbccdd|MODE:IN", "MODE:OUT"],
        )
        self.assertEqual(buffer.feed(b"OUT\n"), ["UID:01020304|MODE:OUT"])
        self.assertEqual(parse_card_event("UID:aabbccdd|MODE:IN"), ("AABBCCDD", "IN"))

    def test_malformed_or_truncated_card_events_are_rejected(self):
        for line in (
            "ID:AABBCCDD",
            "AABBCCDD|TEST",
            "UID:ABC|MODE:IN",
            "UID:AABBCCDD|MODE:INJECT",
            "xxUID:AABBCCDD|MODE:IN",
        ):
            self.assertIsNone(parse_card_event(line))

    def test_overflow_drops_entire_line_then_recovers(self):
        buffer = SerialLineBuffer(max_length=30)
        self.assertEqual(buffer.feed(b"x" * 31 + b"UID:AABBCCDD|MODE:IN\n"), [])
        self.assertEqual(
            buffer.feed(b"UID:AABBCCDD|MODE:OUT\n"), ["UID:AABBCCDD|MODE:OUT"]
        )

    def test_invalid_ascii_does_not_turn_into_a_valid_event(self):
        self.assertEqual(SerialLineBuffer().feed(b"UID:\xffAABBCCDD|MODE:IN\n"), [])
