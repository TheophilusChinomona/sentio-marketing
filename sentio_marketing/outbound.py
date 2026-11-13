"""Frappe 16 queue mixin: recheck policy immediately before standard delivery."""

from sentio_marketing.events import guard_queue, pause_delivery


class ReviewedQueueMixin:
    def send(self, *args, **kwargs):
        guard_queue(self)
        try:
            result = super().send(*args, **kwargs)
        except Exception:
            pause_delivery(self)
            raise
        if self.get("status") == "Error":
            # A transport error pauses outreach, but is not claimed to prove a hard bounce.
            pause_delivery(self)
        return result
