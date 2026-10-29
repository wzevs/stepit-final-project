from django import forms
from django.contrib import admin, messages

from apps.couriers.models import CourierProfile

from .models import Shipment, ShipmentEvent
from .services import (
    InvalidTransition,
    ShipmentError,
    allowed_next,
    assign_courier,
    transition,
    unassign_courier,
)


class ShipmentAdminForm(forms.ModelForm):
    assign_to = forms.ModelChoiceField(
        queryset=CourierProfile.objects.none(),
        required=False,
        help_text="Assign or hand over to this courier. Leave unchanged to keep the current one.",
    )
    clear_courier = forms.BooleanField(
        required=False, help_text="Unassign the courier (ASSIGNED shipments go back to PENDING)."
    )
    new_status = forms.ChoiceField(required=False, choices=[("", "Keep current")])
    transition_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = Shipment
        exclude = ()  # noqa: DJ006 — admin wraps the whole model plus extra action fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        couriers = CourierProfile.objects.filter(is_active=True).select_related("user", "company")
        if self.instance.pk:
            couriers = couriers.filter(company_id=self.instance.company_id)
            self.fields["assign_to"].initial = self.instance.courier_id
            skip = {Shipment.Status.ASSIGNED}
            self.fields["new_status"].choices = [("", "Keep current")] + [
                (status, Shipment.Status(status).label)
                for status in allowed_next(self.instance.status)
                if status not in skip
            ]
        else:
            self.fields.pop("new_status")
            self.fields.pop("clear_courier")
        self.fields["assign_to"].queryset = couriers


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    can_delete = False
    readonly_fields = (
        "kind",
        "from_status",
        "to_status",
        "actor",
        "note",
        "latitude",
        "longitude",
        "data",
        "created_at",
    )
    fields = readonly_fields + ("is_public",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    form = ShipmentAdminForm
    list_display = (
        "tracking_number",
        "status",
        "company",
        "client",
        "courier",
        "recipient_name",
        "recipient_phone",
        "scheduled_delivery_date",
        "created_at",
    )
    list_filter = ("status", "source", "payment_type", "company", "client")
    search_fields = ("tracking_number", "external_id", "recipient_name", "recipient_phone")
    autocomplete_fields = (
        "company",
        "client",
        "pickup_point",
        "pickup_address",
        "delivery_address",
        "created_by",
    )
    readonly_fields = (
        "tracking_number",
        "status",
        "courier",
        "picked_up_at",
        "delivered_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    inlines = [ShipmentEventInline]
    actions = ("action_mark_picked_up", "action_mark_out_for_delivery", "action_mark_delivered")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "tracking_number",
                    "status",
                    "new_status",
                    "transition_note",
                    "source",
                    "external_id",
                )
            },
        ),
        (
            "Ownership",
            {"fields": ("company", "client", "courier", "assign_to", "clear_courier", "created_by")},
        ),
        ("Route", {"fields": ("pickup_point", "pickup_address", "delivery_address")}),
        ("Recipient", {"fields": ("recipient_name", "recipient_phone", "recipient_email")}),
        (
            "Parcel",
            {
                "fields": (
                    "description",
                    "weight_kg",
                    "dimensions_cm",
                    "declared_value",
                    "payment_type",
                    "cod_amount",
                    "is_fragile",
                    "notes",
                )
            },
        ),
        (
            "Timing",
            {"fields": ("scheduled_pickup_at", "scheduled_delivery_date", "picked_up_at", "delivered_at")},
        ),
        (
            "Proof of delivery",
            {"fields": ("proof_photo", "proof_signature", "received_by", "failure_reason")},
        ),
        ("Meta", {"classes": ("collapse",), "fields": ("metadata", "created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ("tracking_number", "courier", "picked_up_at", "delivered_at", "created_at", "updated_at")
        return self.readonly_fields

    def get_fieldsets(self, request, obj=None):
        if obj is not None:
            return super().get_fieldsets(request, obj)
        fieldsets = []
        for title, opts in super().get_fieldsets(request, obj):
            fields = tuple(
                f for f in opts["fields"] if f not in {"new_status", "transition_note", "clear_courier"}
            )
            fieldsets.append((title, {**opts, "fields": fields}))
        return fieldsets

    def save_model(self, request, obj, form, change):
        if not change and obj.status not in {Shipment.Status.DRAFT, Shipment.Status.PENDING}:
            obj.status = Shipment.Status.PENDING
        super().save_model(request, obj, form, change)

        try:
            if (not change) and form.cleaned_data.get("assign_to") and obj.status == Shipment.Status.DRAFT:
                transition(obj, Shipment.Status.PENDING, actor=request.user)
            if form.cleaned_data.get("clear_courier"):
                unassign_courier(obj, actor=request.user, note=form.cleaned_data.get("transition_note", ""))
            else:
                courier = form.cleaned_data.get("assign_to")
                if courier and courier.pk != obj.courier_id:
                    assign_courier(
                        obj, courier, actor=request.user, note=form.cleaned_data.get("transition_note", "")
                    )
            new_status = form.cleaned_data.get("new_status")
            if new_status:
                transition(
                    obj,
                    new_status,
                    actor=request.user,
                    note=form.cleaned_data.get("transition_note", ""),
                    failure_reason=obj.failure_reason,
                    received_by=obj.received_by,
                )
        except (InvalidTransition, ShipmentError) as exc:
            self.message_user(request, str(exc), messages.ERROR)
        else:
            if change and (form.cleaned_data.get("new_status") or form.cleaned_data.get("assign_to")):
                self.message_user(request, f"{obj.tracking_number} is now {obj.get_status_display()}.")

    def _bulk_transition(self, request, queryset, to_status: str) -> None:
        ok = skipped = 0
        for shipment in queryset:
            try:
                transition(shipment, to_status, actor=request.user)
            except (InvalidTransition, ShipmentError):
                skipped += 1
            else:
                ok += 1
        self.message_user(request, f"Updated {ok}, skipped {skipped}.")

    @admin.action(description="Mark picked up")
    def action_mark_picked_up(self, request, queryset):
        self._bulk_transition(request, queryset, Shipment.Status.PICKED_UP)

    @admin.action(description="Mark out for delivery")
    def action_mark_out_for_delivery(self, request, queryset):
        self._bulk_transition(request, queryset, Shipment.Status.OUT_FOR_DELIVERY)

    @admin.action(description="Mark delivered")
    def action_mark_delivered(self, request, queryset):
        self._bulk_transition(request, queryset, Shipment.Status.DELIVERED)


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = ("shipment", "kind", "from_status", "to_status", "actor", "is_public", "created_at")
    list_filter = ("kind", "is_public")
    search_fields = ("shipment__tracking_number", "note")
    autocomplete_fields = ("shipment", "actor")
    readonly_fields = (
        "shipment",
        "kind",
        "from_status",
        "to_status",
        "actor",
        "note",
        "latitude",
        "longitude",
        "data",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
