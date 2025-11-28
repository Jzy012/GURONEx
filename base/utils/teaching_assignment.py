import re
import pandas as pd
import numpy as np
from dateutil.parser import parse as dateutil_parse
import datetime
from django.db.models import Q
from faculty.models import FacultyProfile, Semester, AcademicYear

DAY_MAP = {
    'mon': 'mon', 'monday': 'mon',
    'tue': 'tue', 'tuesday': 'tue',
    'wed': 'wed', 'wednesday': 'wed',
    'thu': 'thu', 'thursday': 'thu',
    'fri': 'fri', 'friday': 'fri',
    'sat': 'sat', 'saturday': 'sat',
}

def normalize_day(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    short = v[:3]
    if short in DAY_MAP:
        return DAY_MAP[short]
    return DAY_MAP.get(v)

def parse_time(value):
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, datetime.time):
        return value
    if hasattr(value, 'time') and not isinstance(value, str):
        try:
            return value.time()
        except Exception:
            pass
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            if 0 < value <= 1:
                seconds = int(round(value * 24 * 3600))
                return datetime.time(hour=(seconds // 3600) % 24,
                                     minute=(seconds % 3600) // 60,
                                     second=seconds % 60)
            else:
                ts = pd.to_datetime('1899-12-30') + pd.to_timedelta(value, unit='D')
                return ts.time()
        except Exception:
            pass
    if isinstance(value, str):
        val = value.strip()
        if not val:
            return None
        try:
            dt = dateutil_parse(val)
            return dt.time()
        except Exception:
            try:
                parts = val.split(':')
                if len(parts) >= 2:
                    h = int(parts[0])
                    m = int(parts[1])
                    s = int(parts[2]) if len(parts) > 2 else 0
                    return datetime.time(hour=h % 24, minute=m % 60, second=s % 60)
            except Exception:
                pass
    return None

def _normalize_header(name: str) -> str:
    if name is None:
        return ''
    s = str(name).strip().lower()
    ALIASES = {
        'subject code': 'subject_code',
        'subjectcode': 'subject_code',
        'subject': 'subject_code',
        'code': 'subject_code',
        'subject description': 'subject_description',
        'description': 'subject_description',
        'year/section': 'year_section',
        'year section': 'year_section',
        'year_section': 'year_section',
        'year': 'year_section',
        'section': 'year_section',
        'day of week': 'day_of_week',
        'day': 'day_of_week',
        'start time': 'start_time',
        'start': 'start_time',
        'time start': 'start_time',
        'end time': 'end_time',
        'end': 'end_time',
        'time end': 'end_time',
        'semester': 'semester',
        'faculty name': 'faculty_name',
        'faculty': 'faculty_name',
        # Room aliases
        'room': 'room',
        'room number': 'room',
        'room_no': 'room',
        'roomnum': 'room',
        'classroom': 'room',
        'rm': 'room',
    }
    key = re.sub(r'[^0-9a-z]+', ' ', s).strip()
    if key in ALIASES:
        return ALIASES[key]
    s2 = re.sub(r'[^0-9a-z]+', '_', s)
    s2 = re.sub(r'_+', '_', s2).strip('_')
    return s2

def read_file_to_rows(file_obj):
    name = getattr(file_obj, 'name', '').lower()
    try:
        if name.endswith('.csv'):
            df = pd.read_csv(file_obj, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(file_obj, dtype=str)
    except Exception as e:
        raise ValueError(f"Unable to read file {getattr(file_obj, 'name', 'uploaded file')}: {e}")

    original_cols = list(df.columns)
    normalized_cols = [_normalize_header(c) for c in original_cols]
    df.columns = normalized_cols

    df = df.replace(r'^\s*$', np.nan, regex=True).dropna(how='all')

    required = {'subject_code', 'subject_description', 'year_section', 'day_of_week', 'start_time', 'end_time'}
    present = set(df.columns)
    if not required.issubset(present):
        missing = required - present
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))} in file {getattr(file_obj, 'name', '')}")

    rows = []
    for idx, raw_row in df.iterrows():
        row_num = idx + 2

        def val(col):
            v = raw_row.get(col)
            if pd.isna(v):
                return ''
            return str(v).strip()

        subject_code = val('subject_code')
        subject_description = val('subject_description')
        year_section = val('year_section')
        day_norm = normalize_day(val('day_of_week'))
        start_t = parse_time(raw_row.get('start_time'))
        end_t = parse_time(raw_row.get('end_time'))
        faculty_name = val('faculty_name') if 'faculty_name' in df.columns else ''
        room_value = val('room') if 'room' in df.columns else ''

        semester_raw = raw_row.get('semester') if 'semester' in df.columns else None
        sem_id = None
        sem_text = ''
        if semester_raw is not None and str(semester_raw).strip() != '':
            sem_text = str(semester_raw).strip()
            try:
                sem_candidate_id = int(float(sem_text))
                if Semester.objects.filter(id=sem_candidate_id).exists():
                    sem_id = sem_candidate_id
            except Exception:
                sem_obj = Semester.objects.filter(
                    Q(academic_year__year_start__icontains=sem_text) | Q(academic_year__year_end__icontains=sem_text)
                ).first()
                if sem_obj:
                    sem_id = sem_obj.id
                else:
                    sem_obj = Semester.objects.filter(
                        Q(semester_type__iexact=sem_text) | Q(semester_type__icontains=sem_text)
                    ).first()
                    if sem_obj:
                        sem_id = sem_obj.id

        rows.append({
            'row_num': row_num,
            'subject_code': subject_code,
            'subject_description': subject_description,
            'year_section': year_section,
            'day_of_week': day_norm,
            'start_time': start_t.isoformat() if start_t else None,
            'end_time': end_t.isoformat() if end_t else None,
            'semester_id': sem_id,
            'semester_text': sem_text,
            'faculty_name': faculty_name,
            'room': room_value,
            'source_file': getattr(file_obj, 'name', ''),
        })
    return rows

def get_all_faculty_list():
    qs = FacultyProfile.objects.all().order_by('name')
    return [{'id': f.id, 'uuid': str(f.uuid), 'name': f.name, 'display': f.name} for f in qs]

def get_all_semesters():
    qs = Semester.objects.select_related('academic_year').order_by('-academic_year__year_start', 'semester_type')
    return [{'id': s.id, 'display': str(s)} for s in qs]