import re
import unicodedata
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

SUFFIX_TOKENS = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}


def _faculty_display_label(faculty):
    name = (getattr(faculty, 'name', '') or '').strip()
    if name:
        return name

    parts = [
        (getattr(faculty, 'first_name', '') or '').strip(),
        (getattr(faculty, 'middle_name', '') or '').strip(),
        (getattr(faculty, 'last_name', '') or '').strip(),
        (getattr(faculty, 'suffix', '') or '').strip(),
    ]
    display = ' '.join([part for part in parts if part]).strip()
    if display:
        return display

    faculty_code = (getattr(faculty, 'faculty_code', '') or '').strip()
    if faculty_code:
        return faculty_code

    return str(getattr(faculty, 'uuid', '') or '').strip()

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


def _normalize_name_for_match(value):
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''

    # Normalize accents and keep only match-relevant separators.
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"['\.]", '', text)
    text = re.sub(r'[^a-z0-9,\s-]+', ' ', text)
    text = text.replace('-', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _strip_suffix_tokens(tokens):
    cleaned = list(tokens)
    while cleaned and cleaned[-1].rstrip('.') in SUFFIX_TOKENS:
        cleaned.pop()
    return cleaned


def _name_variants_from_text(raw_name):
    """
    Build strict-safe normalized variants.
    Supports:
      - Full name as given
      - Last, First (and Last, First Middle)
      - First Last simplification (drops middle/suffix tokens)
    """
    if not raw_name:
        return set()

    variants = set()

    def add_variant(value):
        normalized = _normalize_name_for_match(value)
        if normalized:
            variants.add(normalized)

    raw_text = str(raw_name).strip()
    if not raw_text:
        return variants

    add_variant(raw_text)

    if ',' in raw_text:
        last, rest = raw_text.split(',', 1)
        last = last.strip()
        rest = rest.strip()
        if last and rest:
            add_variant(f"{rest} {last}")
            add_variant(f"{last} {rest}")

    token_source = _normalize_name_for_match(raw_text).replace(',', ' ')
    tokens = [t for t in token_source.split(' ') if t]
    tokens = _strip_suffix_tokens(tokens)

    if len(tokens) >= 2:
        add_variant(' '.join(tokens))
        add_variant(f"{tokens[0]} {tokens[-1]}")

    if len(tokens) >= 1:
        # Allow single-token lookups such as a unique last name.
        add_variant(tokens[-1])

    return variants


def _build_faculty_name_variants(faculty):
    variants = set()

    for name_value in _name_variants_from_text(_faculty_display_label(faculty)):
        variants.add(name_value)

    first = (getattr(faculty, 'first_name', '') or '').strip()
    middle = (getattr(faculty, 'middle_name', '') or '').strip()
    last = (getattr(faculty, 'last_name', '') or '').strip()
    suffix = (getattr(faculty, 'suffix', '') or '').strip()

    if first and last:
        variants.update(_name_variants_from_text(f"{first} {last}"))
        variants.update(_name_variants_from_text(f"{last}, {first}"))
        variants.update(_name_variants_from_text(f"{last} {first}"))

    if first and middle and last:
        variants.update(_name_variants_from_text(f"{first} {middle} {last}"))
        variants.update(_name_variants_from_text(f"{last}, {first} {middle}"))

    if first and middle and last and suffix:
        variants.update(_name_variants_from_text(f"{first} {middle} {last} {suffix}"))

    return variants


def build_faculty_name_index():
    qs = FacultyProfile.objects.all().only('uuid', 'name', 'first_name', 'middle_name', 'last_name', 'suffix')
    match_map = {}
    display_map = {}

    for faculty in qs:
        faculty_uuid = str(faculty.uuid)
        display_map[faculty_uuid] = _faculty_display_label(faculty)

        for variant in _build_faculty_name_variants(faculty):
            match_map.setdefault(variant, set()).add(faculty_uuid)

    return {'match_map': match_map, 'display_map': display_map}


def match_faculty_from_name(raw_name, faculty_name_index):
    variants = _name_variants_from_text(raw_name)
    if not variants:
        return {
            'status': 'empty',
            'faculty_uuid': None,
            'message': '',
        }

    match_map = faculty_name_index.get('match_map', {})
    display_map = faculty_name_index.get('display_map', {})

    matched_uuids = set()
    for variant in variants:
        matched_uuids.update(match_map.get(variant, set()))

    if len(matched_uuids) == 1:
        matched_uuid = next(iter(matched_uuids))
        return {
            'status': 'matched',
            'faculty_uuid': matched_uuid,
            'faculty_display': display_map.get(matched_uuid, 'faculty record'),
            'message': f"Auto-matched to {display_map.get(matched_uuid, 'faculty record')}",
        }

    source_label = (raw_name or '').strip()
    if len(matched_uuids) == 0:
        return {
            'status': 'no_match',
            'faculty_uuid': None,
            'message': f"No faculty match found for '{source_label}'.",
        }

    candidate_names = sorted(display_map.get(uid, uid) for uid in matched_uuids)
    preview = ', '.join(candidate_names[:3])
    if len(candidate_names) > 3:
        preview += ', ...'
    return {
        'status': 'ambiguous',
        'faculty_uuid': None,
        'message': f"Ambiguous faculty name '{source_label}' ({preview}). Please select manually.",
    }

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
    return [{'id': f.id, 'uuid': str(f.uuid), 'name': f.name, 'display': _faculty_display_label(f)} for f in qs]

def get_all_semesters():
    qs = Semester.objects.select_related('academic_year').order_by('-academic_year__year_start', 'semester_type')
    return [{'id': s.id, 'display': str(s)} for s in qs]