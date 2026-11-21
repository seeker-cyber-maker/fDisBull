"""Authenticated ownership coordination with no emulator or game backend.

Reuse the service's transport, credentials, descriptors and publisher dispatch.
Status describes this coordinator only; it never invents native game state.
"""

from .service import PROTOCOL, TURN_OPS, PlayService, ProtocolError, authorized


class CoordinationService(PlayService):
    descriptor_kind = "ownership-coordinator"

    def __init__(self, directory, ownership_viewer, *, client_timeout=1.0,
                 credential_factory=None):
        if ownership_viewer is None:
            raise ValueError("An ownership coordinator requires a viewer binding")
        # The inherited transport invokes its factory once. There is deliberately
        # no backend object, and inherited cleanup therefore closes no emulator.
        super().__init__(lambda: None, directory, client_timeout=client_timeout,
                         credential_factory=credential_factory,
                         ownership_viewer=ownership_viewer)

    def _start_harness_input(self):
        """A coordinator has no native input to transfer or resume."""

    def snapshot(self):
        return {"instance_id": self.instance_id, "kind": "ownership-coordinator",
                "platform_takeover": self.ownership.status()}

    def _dispatch(self, request, credential):
        if not authorized(request, credential):
            raise ProtocolError("unauthorized", "Authentication required.")
        if (set(request) - {"protocol", "id", "token", "op", "params", "instance_id"}
                or request.get("protocol") != PROTOCOL):
            raise ProtocolError("invalid_request", "Invalid coordinator request.")
        if request.get("instance_id") != self.instance_id:
            raise ProtocolError("stale_instance", "Read this coordinator's current instance before acting.")
        op, params = request.get("op"), request.get("params", {})
        if not isinstance(op, str) or not isinstance(params, dict):
            raise ProtocolError("invalid_request", "Operation and object params are required.")
        if op not in TURN_OPS | {"status", "coordinator-close"}:
            raise ProtocolError("unknown_operation", "This ownership coordinator exposes no game or native input operations.")
        if op in {"status", "coordinator-close"}:
            if params:
                raise ProtocolError("invalid_params", "This operation accepts no params.")
            if op == "status":
                return self.snapshot()
            self.stop_requested.set()
            return {"status": "closing"}
        expected = {"controller_id"} if op == "turn-claim" else {"lease"}
        if set(params) != expected:
            raise ProtocolError("invalid_params", "Invalid turn parameters.")
        try:
            if op == "turn-claim":
                return self.ownership.claim(params["controller_id"])
            if op == "turn-check":
                return self.ownership.check(params["lease"])
            return self.ownership.release(params["lease"])
        except ValueError as error:
            raise ProtocolError("turn_unavailable", str(error)) from error
