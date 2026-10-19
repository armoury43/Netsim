"""Tests for netsim.core.events."""

from __future__ import annotations

import unittest

from netsim.core.events import Event, EventBus


class TestEventBus(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus()

    def test_subscriber_receives_published_event(self) -> None:
        received: list[Event] = []
        self.bus.subscribe("link.up", received.append)

        event = Event(name="link.up", payload={"iface": "Gi0/0"})
        self.bus.publish(event)

        self.assertEqual(received, [event])

    def test_subscriber_does_not_receive_other_event_names(self) -> None:
        received: list[Event] = []
        self.bus.subscribe("link.up", received.append)

        self.bus.publish(Event(name="link.down"))

        self.assertEqual(received, [])

    def test_multiple_subscribers_all_receive_event_in_order(self) -> None:
        call_order: list[str] = []
        self.bus.subscribe("x", lambda e: call_order.append("first"))
        self.bus.subscribe("x", lambda e: call_order.append("second"))

        self.bus.publish(Event(name="x"))

        self.assertEqual(call_order, ["first", "second"])

    def test_unsubscribe_stops_further_delivery(self) -> None:
        received: list[Event] = []
        unsubscribe = self.bus.subscribe("x", received.append)

        self.bus.publish(Event(name="x"))
        unsubscribe()
        self.bus.publish(Event(name="x"))

        self.assertEqual(len(received), 1)

    def test_unsubscribe_twice_is_a_no_op(self) -> None:
        unsubscribe = self.bus.subscribe("x", lambda e: None)
        unsubscribe()
        unsubscribe()

    def test_publish_with_no_subscribers_is_a_no_op(self) -> None:
        self.bus.publish(Event(name="nobody.listening"))

    def test_failing_handler_does_not_block_other_handlers(self) -> None:
        received: list[str] = []

        def failing_handler(_event: Event) -> None:
            raise RuntimeError("simulated subscriber failure")

        def healthy_handler(_event: Event) -> None:
            received.append("ok")

        self.bus.subscribe("x", failing_handler)
        self.bus.subscribe("x", healthy_handler)

        self.bus.publish(Event(name="x"))

        self.assertEqual(received, ["ok"])

    def test_clear_specific_event_name(self) -> None:
        received: list[Event] = []
        self.bus.subscribe("x", received.append)
        self.bus.subscribe("y", received.append)

        self.bus.clear("x")
        self.bus.publish(Event(name="x"))
        self.bus.publish(Event(name="y"))

        self.assertEqual(len(received), 1)

    def test_clear_all(self) -> None:
        received: list[Event] = []
        self.bus.subscribe("x", received.append)
        self.bus.subscribe("y", received.append)

        self.bus.clear()
        self.bus.publish(Event(name="x"))
        self.bus.publish(Event(name="y"))

        self.assertEqual(received, [])


class TestEvent(unittest.TestCase):
    def test_payload_defaults_to_empty_dict(self) -> None:
        event = Event(name="test")
        self.assertEqual(event.payload, {})

    def test_is_frozen(self) -> None:
        event = Event(name="test")
        with self.assertRaises(Exception):
            event.name = "changed"

if __name__ == "__main__":
    unittest.main()
