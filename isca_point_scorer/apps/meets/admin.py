from django.contrib import admin
from isca_point_scorer.apps.meets.models import Meet, Team, Swimmer, Event, Result

@admin.register(Meet)
class MeetAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'course', 'is_published', 'is_processed')
    list_filter = ('is_published', 'is_processed', 'course')
    search_fields = ('name', 'location')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'meet')
    list_filter = ('meet',)
    search_fields = ('name', 'code')

@admin.register(Swimmer)
class SwimmerAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'gender', 'age', 'team')
    list_filter = ('gender', 'meet', 'team')
    search_fields = ('first_name', 'last_name', 'meet_id')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('event_number', 'name', 'meet', 'distance', 'stroke', 'gender', 'is_relay')
    list_filter = ('meet', 'gender', 'stroke', 'is_relay')
    search_fields = ('name', 'event_number')

@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ('swimmer', 'event', 'finals_time', 'finals_place', 'points', 'is_disqualified')
    list_filter = ('event__meet', 'is_disqualified', 'event')
    search_fields = ('swimmer__first_name', 'swimmer__last_name')