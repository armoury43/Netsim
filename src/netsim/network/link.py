"""The virtual link abstraction.

A :class:`Link` connects exactly two interfaces (identified by
device ID + interface name pairs, not object references - this keeps
links trivially serializable/inspectable for a future GUI without
holding onto live device objects). State is deterministic: a link is
``up`` or it isn't; nothing here simulates propagation delay, jitter,
or packet loss, per the project's "deterministic correctness over
visual realism" directive.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    """One side of a link: a specific interface on a specific device.

    Attributes:
        device_id: The owning device's :attr:`~netsim.devices.base.Device.device_id`.
        interface_name: The interface name on that device.
    """

    device_id: str
    interface_name: str


class Link:
    """A point-to-point connection between two interfaces.

    Args:
        endpoint_a: One side of the link.
        endpoint_b: The other side of the link.
    """

    def __init__(self, endpoint_a: Endpoint, endpoint_b: Endpoint) -> None:
        self.endpoint_a = endpoint_a
        self.endpoint_b = endpoint_b
        self._up = True

    @property
    def up(self) -> bool:
        """Whether this link is currently passing traffic."""
        return self._up

    def set_up(self, up: bool) -> None:
        """Set the link's up/down state (simulating unplugging a cable, etc.)."""
        self._up = up

    def involves(self, device_id: str, interface_name: str) -> bool:
        """Whether this link has an endpoint matching the given device+interface."""
        return Endpoint(device_id, interface_name) in (self.endpoint_a, self.endpoint_b)

    def other_end(self, endpoint: Endpoint) -> Endpoint:
        """Given one endpoint of this link, return the endpoint at the other end.

        Args:
            endpoint: Must equal one of this link's two endpoints.

        Returns:
            The endpoint at the other end of the link.

        Raises:
            ValueError: If ``endpoint`` is neither endpoint of this link.
        """
        if endpoint == self.endpoint_a:
            return self.endpoint_b
        if endpoint == self.endpoint_b:
            return self.endpoint_a
        raise ValueError(f"{endpoint!r} is not an endpoint of this link")

    def __repr__(self) -> str:
        return f"Link({self.endpoint_a!r} <-> {self.endpoint_b!r}, up={self._up})"
