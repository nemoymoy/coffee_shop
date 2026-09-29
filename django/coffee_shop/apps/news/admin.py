"""Admin for news app."""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import News, Promotion


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_published', 'published_at', 'created_at']
    list_filter = ['is_published']
    search_fields = ['title', 'content']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_published']
    date_hierarchy = 'published_at'

    def get_list_display(self, request):
        return self.list_display

    def get_search_results(self, request, qs, search_params):
        return qs, False


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'is_current', 'start_date', 'end_date']
    list_filter = ['is_active']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ['is_active']
    date_hierarchy = 'start_date'

    def get_list_display(self, request):
        return self.list_display

    def get_search_results(self, request, qs, search_params):
        return qs, False
