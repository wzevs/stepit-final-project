from django.contrib import admin

from .models import CompanyMembership, CourierCompany


class CompanyMembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(CourierCompany)
class CourierCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tracking_prefix", "contact_phone", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "legal_name", "tax_id", "tracking_prefix")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CompanyMembershipInline]


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_active")
    list_filter = ("role", "is_active", "company")
    autocomplete_fields = ("user", "company")
