"""PvE semantic dispatcher backed only by the injected native action channel."""

from __future__ import annotations

from shadowbane_lab.client_extension import NativeExtensionActionDispatcher
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.pve.model import PvEIntent


class NativeExtensionPvEIntentDispatcher:
    """Submit PvE intents to the injected extension without desktop-input fallback."""

    def __init__(self, dispatcher: NativeExtensionActionDispatcher) -> None:
        if not isinstance(dispatcher, NativeExtensionActionDispatcher):
            raise ValueError("dispatcher must be NativeExtensionActionDispatcher")
        self._dispatcher = dispatcher

    @property
    def name(self) -> str:
        return f"pve/{self._dispatcher.name}"

    @property
    def dispatcher(self) -> NativeExtensionActionDispatcher:
        return self._dispatcher

    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult:
        if not isinstance(intent, PvEIntent):
            raise ValueError("intent must be PvEIntent")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        return self._dispatcher.dispatch_action(
            intent.value,
            correlation_id=f"pve:{sequence}:{intent.value}",
        )
