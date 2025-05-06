from django.contrib import admin
from django.utils.html import format_html
import json

from isca_point_scorer.apps.scoring.models import PointSystem, MeetScoring

@admin.register(PointSystem)
class PointSystemAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'is_active', 'event_count')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    
    def event_count(self, obj):
        data = obj.data
        event_count = 0
        for gender, events in data.items():
            event_count += len(events)
        return event_count
    event_count.short_description = 'Number of Events'

@admin.register(MeetScoring)
class MeetScoringAdmin(admin.ModelAdmin):
    list_display = ('meet', 'point_system', 'include_exhibition_swims', 'include_relay_events')
    list_filter = ('include_exhibition_swims', 'include_relay_events', 'point_system')
    search_fields = ('meet__name',)