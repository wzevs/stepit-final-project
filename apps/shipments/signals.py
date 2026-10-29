from django.dispatch import Signal

# Sent after the transaction that changed the status has committed.
# kwargs: shipment, from_status, to_status, actor, event
shipment_status_changed = Signal()

# Sent after the transaction that changed the courier has committed.
# kwargs: shipment, previous_courier, courier, actor
shipment_courier_changed = Signal()
