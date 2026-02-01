from django.shortcuts import render

# Create your views here.


from datetime import datetime, time
import calendar
import pytz

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.cache import cache
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from faculty.models import FacultyProfile
from .models import RFIDTag, AttendanceLog


@csrf_exempt
@require_POST
def pair_rfid_api(request):
    faculty_id = request.POST.get("faculty_id")
    rfid_uid = request.POST.get("rfid_uid")
    if not faculty_id or not rfid_uid:
        return JsonResponse({"error": "Missing data"}, status=400)
    try:
        tag = RFIDTag.objects.get(uid=rfid_uid)
    except RFIDTag.DoesNotExist:
        return JsonResponse({"error": "RFID not found"}, status=404)
    if tag.faculty:
        return JsonResponse({"error": f'RFID already paired to {tag.faculty.name}'}, status=400)
    try:
        faculty = FacultyProfile.objects.get(uuid=faculty_id)
    except FacultyProfile.DoesNotExist:
        return JsonResponse({"error": "Faculty not found"}, status=404)
    tag.faculty = faculty
    tag.save()
    return JsonResponse({"success": True, "faculty": faculty.name, "uid": tag.uid})

@csrf_exempt
@require_POST
def rfid_tap_api(request):
    uid = request.POST.get("uid")
    if not uid:
        return JsonResponse({"error": "No UID"}, status=400)

    uid = uid.strip().upper()  # normalize hex from ESP32

    cache.set('last_rfid_uid', uid, timeout=10)
    tag, created = RFIDTag.objects.get_or_create(uid=uid)
    if tag.faculty is not None:
        return JsonResponse({"status": "paired", "uid": uid, "faculty": tag.faculty.name})
    return JsonResponse({"status": "unpaired", "uid": uid})

def format_log(log):
    tz = pytz.timezone('Asia/Manila')
    time_in = timezone.localtime(log.time_in).astimezone(tz) if log.time_in else None
    time_out = timezone.localtime(log.time_out).astimezone(tz) if log.time_out else None
    date_str = log.date.strftime('%b %d, %Y') if log.date else '-'
    return {
        'faculty': log.faculty.name,
        'date': date_str,
        'time_in': time_in.strftime('%I:%M %p') if time_in else '-',
        'time_out': time_out.strftime('%I:%M %p') if time_out else '-',
    }

@api_view(['POST'])
def log_attendance(request):
    uid = request.data.get('uid')
    if not uid:
        return Response({"error": "UID missing"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        rfid_tag = RFIDTag.objects.get(uid__iexact=uid)
    except RFIDTag.DoesNotExist:
        RFIDTag.objects.create(uid=uid)
        return Response({
            "error": "UID not registered. Please pair this UID in the admin.",
            "uid": uid
        }, status=status.HTTP_404_NOT_FOUND)

    faculty = rfid_tag.faculty
    if not faculty:
        return Response({
            "error": "UID found but not paired to any faculty. Please assign in admin.",
            "uid": uid
        }, status=status.HTTP_400_BAD_REQUEST)

    today = timezone.localdate()
    time_now = timezone.now()
    log, created = AttendanceLog.objects.get_or_create(
        faculty=faculty,
        date=today,
        defaults={'uid': uid, 'time_in': time_now}
    )

    log_dict = format_log(log)

    if created:
        return Response({
            "message": "Time-In recorded",
            "faculty": faculty.name,
            "status": "IN",
            "time_in": log_dict["time_in"]
        }, status=status.HTTP_201_CREATED)
    elif log.time_out is None:
        log.time_out = time_now
        log.save()
        log_dict = format_log(log)
        return Response({
            "message": "Time-Out recorded",
            "faculty": faculty.name,
            "status": "OUT",
            "time_out": log_dict["time_out"]
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "message": "Attendance already complete for today (both IN and OUT recorded).",
            "faculty": faculty.name,
            "status": "DONE",
            "time_in": log_dict["time_in"],
            "time_out": log_dict["time_out"]
        }, status=status.HTTP_200_OK)







from django.shortcuts import render
from .models import ESP32WiFi
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
from django.utils import timezone
import json
from rfid.models import FacultyProfile, RFIDTag, AttendanceLog
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now

    # Create your views here.



@require_GET
def check_wifi_reset(request):
    # Fetch the first (or specific) ESP32 device from the database
    wifi_config = ESP32WiFi.objects.first()
    if not wifi_config:
        return JsonResponse({'error': 'No ESP32 WiFi config found'}, status=404)

    if wifi_config.reset_wifi:
        # ESP detected reset request
        wifi_config.reset_wifi = False  # Clear the flag to prevent loop
        wifi_config.save()
        return JsonResponse({'reset': True})
    else:
        return JsonResponse({'reset': False})
