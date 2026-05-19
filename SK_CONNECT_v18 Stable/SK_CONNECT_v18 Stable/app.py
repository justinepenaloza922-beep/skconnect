import os
from typing import Optional, Dict, Any
from functools import wraps
from flask import Flask, send_file, render_template, request, redirect, url_for, session, flash, jsonify, Response
import traceback
import re
from supabase import create_client
from datetime import datetime,  timezone, timedelta
from dotenv import load_dotenv
import json
import uuid
from werkzeug.utils import secure_filename
import sqlite3
from flask import g
from fpdf import FPDF
import hashlib
import smtplib
from email.mime.text import MIMEText
import random
from httpx import ReadError
import time
import csv
from io import StringIO
from io import BytesIO
QR_AVAILABLE = True
try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
except Exception as _err:
    QR_AVAILABLE = False
    qrcode = None
    Image = ImageDraw = ImageFont = None
    # Defer logging until app exists
from collections import Counter
import shutil
import socket
from zoneinfo import ZoneInfo  # Python 3.9+
from flask_cors import CORS
try:
    from pywebpush import webpush, WebPushException
    PYWEBPUSH_AVAILABLE = True
except Exception:
    PYWEBPUSH_AVAILABLE = False
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except Exception:
    TWILIO_AVAILABLE = False


load_dotenv()


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this!
# after app = Flask(__name__) or similar
CORS(app, origins="*", supports_credentials=True)


# --- Supabase config ---
url = os.environ.get("SUPABASE_URL")  # fixed typo
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in the environment variables.")

supabase = create_client(url, key)

UPLOAD_FOLDER = 'static/uploads/reports'
ALLOWED_EXTENSIONS = {
    'pdf',
    'xlsx', 'xls',
    'doc', 'docx',
    'ppt', 'pptx',   # ⬅️ ito ang importante
     'mp4', 'mov', 'avi'
}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 10 MB

TRAINING_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'training')
os.makedirs(TRAINING_UPLOAD_FOLDER, exist_ok=True)

def send_email_stub(to_emails, subject, body):
    # real SMTP sending if configured; fallback to Gmail when only SMTP_EMAIL/SMTP_PASSWORD are set
    smtp_host = os.environ.get('SMTP_HOST') or 'smtp.gmail.com'
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER') or os.environ.get('SMTP_EMAIL')
    smtp_pass = os.environ.get('SMTP_PASS') or os.environ.get('SMTP_PASSWORD')
    from_addr = os.environ.get('FROM_EMAIL') or smtp_user
    if smtp_host and smtp_user and smtp_pass and from_addr and to_emails:
        sent_count = 0
        failed = []
        chunk_size = int(os.environ.get('SMTP_CHUNK_SIZE', 50))
        app.logger.info(f"send_email_stub: sending to {len(to_emails)} recipients in chunks of {chunk_size}")
        try:
            for chunk_start in range(0, len(to_emails), chunk_size):
                chunk = to_emails[chunk_start:chunk_start + chunk_size]
                server = smtplib.SMTP(smtp_host, smtp_port)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                for e in chunk:
                    try:
                        msg = MIMEText(body or '', 'plain', 'utf-8')
                        msg['Subject'] = subject or ''
                        msg['From'] = from_addr
                        msg['To'] = e
                        send_result = server.sendmail(from_addr, e, msg.as_string())
                        if send_result:
                            failed.append({'email': e, 'error': str(send_result)})
                            app.logger.error(f"Sendmail reported failure for {e}: {send_result}")
                        else:
                            sent_count += 1
                    except Exception as ex:
                        failed.append({'email': e, 'error': str(ex)})
                        app.logger.error(f"Error sending email to {e}: {ex}")
                server.quit()
            app.logger.info(f"Sent emails to {sent_count} recipients, failed={len(failed)}")
            return {
                'success': len(failed) == 0,
                'sent': sent_count,
                'failed': failed,
                'stub': False,
                'error': None,
                'smtp_host': smtp_host,
                'smtp_user': smtp_user
            }
        except Exception as e:
            app.logger.error(f"SMTP send error: {e}")
            return {
                'success': False,
                'sent': sent_count,
                'failed': [{'email': 'all', 'error': str(e)}],
                'stub': False,
                'error': str(e),
                'smtp_host': smtp_host,
                'smtp_user': smtp_user
            }
    else:
        app.logger.info(f"[stub] send_email to={len(to_emails)} subject={subject}")
        return {
            'success': False,
            'sent': 0,
            'failed': [{'email': e, 'error': 'SMTP not configured'} for e in to_emails],
            'stub': True,
            'error': 'SMTP not configured',
            'smtp_host': smtp_host,
            'smtp_user': smtp_user
        }

def send_sms_stub(to_numbers, body):
    # Use Twilio if configured, otherwise log. Record each send into `sms_send_logs`.
    tw_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    tw_token = os.environ.get('TWILIO_AUTH_TOKEN')
    tw_from = os.environ.get('TWILIO_FROM_NUMBER')
    if TWILIO_AVAILABLE and tw_sid and tw_token and tw_from:
        try:
            client = TwilioClient(tw_sid, tw_token)
            for num in to_numbers:
                if not num:
                    continue
                result = send_single_sms(num, body)
                # write log entry for each attempt
                try:
                    supabase.table('sms_send_logs').insert({
                        'phone': num,
                        'status': result.get('status'),
                        'message_sid': result.get('message_sid'),
                        'error': result.get('error'),
                        'body': body,
                        'sent_at': datetime.utcnow().isoformat()
                    }).execute()
                except Exception as _e:
                    app.logger.debug(f"Could not write sms_send_logs: {_e}")
            app.logger.info(f"Processed SMS sends for {len(to_numbers)} recipients")
        except Exception as e:
            app.logger.error(f"Twilio client error: {e}")
    else:
        # log and write stub entries for visibility
        app.logger.info(f"[stub] send_sms to={len(to_numbers)} body={body[:60]}")
        for num in to_numbers:
            try:
                supabase.table('sms_send_logs').insert({
                    'phone': num,
                    'status': 'stub',
                    'body': body,
                    'sent_at': datetime.utcnow().isoformat()
                }).execute()
            except Exception:
                pass


def send_single_sms(phone, body):
    """Attempt to send a single SMS, return a dict with status/message_sid/error."""
    tw_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    tw_token = os.environ.get('TWILIO_AUTH_TOKEN')
    tw_from = os.environ.get('TWILIO_FROM_NUMBER')
    if TWILIO_AVAILABLE and tw_sid and tw_token and tw_from:
        try:
            client = TwilioClient(tw_sid, tw_token)
            msg = client.messages.create(body=body, from_=tw_from, to=phone)
            return {'status': 'sent', 'message_sid': getattr(msg, 'sid', None), 'error': None}
        except Exception as ex:
            app.logger.error(f"Twilio send error to {phone}: {ex}")
            return {'status': 'failed', 'message_sid': None, 'error': str(ex)}
    else:
        # stub path
        app.logger.info(f"[stub] send_single_sms to={phone} body={body[:60]}")
        return {'status': 'stub', 'message_sid': None, 'error': None}

def send_webpush_stub(subscriptions, payload):
    vapid_subject = os.environ.get('VAPID_SUBJECT') or 'mailto:admin@example.com'
    vapid_public = os.environ.get('VAPID_PUBLIC_KEY')
    vapid_private = os.environ.get('VAPID_PRIVATE_KEY')
    if PYWEBPUSH_AVAILABLE and vapid_public and vapid_private:
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info=sub,
                    data=json.dumps(payload),
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": vapid_subject}
                )
            except WebPushException as ex:
                app.logger.error(f"WebPush error: {ex}")
    else:
        app.logger.info(f"[stub] send_webpush to={len(subscriptions)} payload={payload}")

def process_scheduled_announcements():
    try:
        now_iso = datetime.utcnow().isoformat()
        # find announcements scheduled to post and not yet sent
        resp = supabase.table('announcements').select('*').eq('schedule_post', True).eq('scheduled_sent', False).execute()
        rows = resp.data if getattr(resp, 'data', None) is not None else []
        for ann in rows:
            sched = ann.get('schedule_time')
            if not sched:
                continue
            # compare ISO strings or parse to datetime
            try:
                sched_dt = datetime.fromisoformat(sched)
            except Exception:
                # try stripping timezone
                try:
                    sched_dt = datetime.fromisoformat(sched.replace('Z',''))
                except Exception:
                    continue
            if sched_dt <= datetime.utcnow():
                # perform send (stubs)
                users_resp = supabase.table('sk_users').select('id,email,phone').execute()
                users = users_resp.data if getattr(users_resp, 'data', None) is not None else []
                emails = [u.get('email') for u in users if u.get('email')]
                phones = [u.get('phone') for u in users if u.get('phone')]
                # call real senders where possible
                # WebPush: fetch stored subscriptions
                subs_resp = supabase.table('push_subscriptions').select('*').execute()
                subs = subs_resp.data if getattr(subs_resp, 'data', None) is not None else []
                subscriptions = [s.get('subscription') for s in subs if s.get('subscription')]
                if subscriptions:
                    send_webpush_stub(subscriptions, {'title': ann.get('title'), 'body': ann.get('description'), 'id': ann.get('id')})
                # Email
                if emails:
                    send_result = send_email_stub(emails, ann.get('title'), ann.get('description'))
                    if send_result['success']:
                        app.logger.info(f"Scheduled announcement email sent to {send_result['sent']} users.")
                    elif send_result['stub']:
                        app.logger.info("Scheduled announcement email request logged as stub because SMTP is not configured.")
                    else:
                        app.logger.warning(f"Scheduled announcement email had {len(send_result['failed'])} failures.")
                # SMS (still stub)
                if phones:
                    send_sms_stub(phones, ann.get('description'))
                # update notifications_sent counter (add user count)
                try:
                    cur_sent = int(ann.get('notifications_sent') or 0)
                except Exception:
                    cur_sent = 0
                new_sent = cur_sent + max(1, len(users))
                supabase.table('announcements').update({'notifications_sent': new_sent, 'scheduled_sent': True}).eq('id', ann.get('id')).execute()
                app.logger.info(f"Scheduled announcement {ann.get('id')} processed, notifications_sent={new_sent}")
    except Exception as e:
        app.logger.error(f"Error in scheduled announcements job: {e}")


# --- Supabase config ---
url = os.environ.get("SUPABASE_URL")  # fixed typo
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in the environment variables.")

supabase = create_client(url, key)

UPLOAD_FOLDER = 'static/uploads/reports'
ALLOWED_EXTENSIONS = {'pdf', 'xlsx', 'xls', 'doc', 'docx', 'csv', 'txt', 'jpg', 'jpeg', 'png', 'gif', 'ppt', 'pptx', 'odt', 'ods'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB


# Helper function to verify if an image exists in static folder
def verify_image_exists(image_path):
    if not image_path:
        return None
    full_path = os.path.join(app.static_folder, 'images', image_path)
    if os.path.isfile(full_path):
        return url_for('static', filename=f'images/{image_path}')
    return url_for('static', filename='images/default_event.jpg')  # Fallback to default image


@app.route('/api/events')
def get_events():
    try:
        # Query upcoming events from Supabase
        response = supabase.table('events').select('*').execute()
        events = response.data

        # Transform events into FullCalendar format
        calendar_events = []
        for event in events:
            # Base calendar event data
            calendar_event = {
                'id': str(event.get('id')),
                'title': event.get('name', 'Untitled Event'),
                'start': event.get('date'),
                'allDay': True,  # Default to all-day events
                'extendedProps': {
                    'type': event.get('type'),
                    'description': event.get('description'),
                    'location': event.get('location'),
                    'max_participants': event.get('max_participants'),
                    'required_items': event.get('required_items', []),
                    'registration_deadline': event.get('registration_deadline'),
                    'budget': event.get('budget'),
                    'cover_image_url': verify_image_exists(event.get('cover_image_url')),
                    'enable_qr': event.get('enable_qr', False),
                    'created_at': event.get('created_at'),
                    'organizers': event.get('organizers', []),
                    'start_time': event.get('start_time'),
                    'end_time': event.get('end_time')
                }
            }

            # Handle start and end times
            event_date = event.get('date')
            if event_date:
                start_time = event.get('start_time')
                end_time = event.get('end_time')
                
                if start_time:
                    calendar_event['start'] = f"{event_date}T{start_time}"
                    calendar_event['allDay'] = False
                if end_time:
                    calendar_event['end'] = f"{event_date}T{end_time}"

            # Clean up extended props - remove None values
            calendar_event['extendedProps'] = {
                k: v for k, v in calendar_event['extendedProps'].items() 
                if v is not None
            }
            
            calendar_events.append(calendar_event)

        return jsonify(calendar_events)
    except Exception as e:
        app.logger.error(f"Error fetching events: {str(e)}")
        return jsonify({'error': 'Failed to fetch events'}), 500


@app.route('/api/projects')
def get_projects():
    try:
        # Query projects from Supabase
        response = supabase.table('projects').select('*').execute()
        projects = response.data

        # Transform projects into calendar events format
        calendar_projects = []
        for project in projects:
            # Make sure dates are properly formatted for the calendar
            start_date = project.get('start_date')
            end_date = project.get('end_date')
            
            if start_date and not isinstance(start_date, str):
                start_date = start_date.isoformat()
            if end_date and not isinstance(end_date, str):
                end_date = end_date.isoformat()

            # Format the project data for the calendar
            calendar_project = {
                'id': f"project_{project.get('id')}",  # Prefix to distinguish from events
                'title': project.get('name', 'Untitled Project'),
                'start': start_date,
                'end': end_date,
                'allDay': True,  # Projects are typically shown as all-day events
                'backgroundColor': '#10B981',  # Green color for projects
                'borderColor': '#059669',
                'extendedProps': {
                    'isProject': True,
                    'type': 'Project',
                    'category': project.get('category'),
                    'description': project.get('description'),
                    'budget': project.get('budget_allocated'),
                    'amount_spent': project.get('amount_spent'),
                    'status': project.get('status'),
                    'project_manager': project.get('project_manager'),
                    'created_at': project.get('created_at')
                }
            }

            # Clean up extended props - remove None values
            calendar_project['extendedProps'] = {
                k: v for k, v in calendar_project['extendedProps'].items() 
                if v is not None
            }
            
            calendar_projects.append(calendar_project)

        return jsonify(calendar_projects)

    except Exception as e:
        app.logger.error(f"Error fetching projects: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Get local IP address
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    finally:
        s.close()
    return IP
# Update the QR code generation JavaScript

def format_datetime(dt_str, fmt='%Y-%m-%d %H:%M:%S', to_tz=None):
    """Parse an ISO datetime string and format it. If to_tz is None, use UTC-to-naive representation."""
    if not dt_str:
        return ''
    try:
        # accept trailing Z or +00:00 etc.
        dt = datetime.fromisoformat(str(dt_str).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            # assume UTC if no tzinfo
            dt = dt.replace(tzinfo=timezone.utc)
        if to_tz:
            tz = ZoneInfo(to_tz)
            dt = dt.astimezone(tz)
        else:
            # normalize to UTC then drop tzinfo for display
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime(fmt)
    except Exception:
        return dt_str  # fallback to original if parse fails

def is_allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def detailed_time_ago(dt_str):
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - dt

    seconds = diff.total_seconds()
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        return f"{int(seconds // 60)} minutes ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)} hours ago"
    elif seconds < 604800:
        return f"{int(seconds // 86400)} days ago"
    else:
        return f"{int(seconds // 604800)} weeks ago"

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(recipient_email, otp):
    sender_email = os.environ.get("SMTP_EMAIL")
    sender_password = os.environ.get("SMTP_PASSWORD")
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    subject = "Your SK Connect Registration OTP"
    body = f"Your OTP for registration is: {otp}\nThis code will expire in 10 minutes."

    msg = MIMEText(body)
    msg["Subject"] = subject
    if not sender_email:
        raise ValueError("SMTP_EMAIL environment variable is not set.")
    if not sender_password:
        raise ValueError("SMTP_PASSWORD environment variable is not set.")
    msg["From"] = sender_email
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print("Email send error:", e)
        return False



# ----------------- helpers -----------------
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def time_ago(dt_str):
    try:
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
    except Exception:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - dt
    s = int(diff.total_seconds())
    if s < 60:
        return f"{s}s ago"
    m = s // 60
    if m < 60:
        return f"{m}m ago"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    d = h // 24
    return f"{d} day{'s' if d != 1 else ''} ago"


@app.context_processor
def inject_helpers():
    return dict(
        time_ago=time_ago,
        get_default_profile_image=get_default_profile_image,
        current_user=get_current_user(),
        format_datetime=format_datetime,
    )


# single, consistent version
def get_current_user() -> Optional[Dict[str, Any]]:
    """Return a dict from session (set at login/signup)."""
    if 'user_id' not in session:
        return None
    return {
        'id': session.get('user_id'),
        'username': session.get('username'),
        'full_name': session.get('full_name'),
        'position': session.get('position'),
        'role_id': session.get('role_id'),
        'barangay': session.get('barangay'),
        'gender': session.get('gender'),
    }

def get_user_attribute(user: Optional[Dict[str, Any]], attribute: str, default: str = "Unknown User") -> str:
    """Safely get a user attribute with a fallback default value."""
    if user is None:
        return default
    return user.get(attribute, default)

def get_default_profile_image(user: Optional[Dict[str, Any]]) -> str:
    """Get the appropriate default profile image based on user's gender."""
    if user is None:
        return '/static/images/default_male.png'
    
    gender = user.get('gender', '') or ''  # Handle None case
    gender = gender.lower() if gender else ''
    if gender == 'female':
        return '/static/images/default_female.png'
    elif gender == 'prefer not to say':
        return '/static/images/default_prefer_not_to_say.png'
    else:  # male or any other value defaults to male
        return '/static/images/default_male.png'


# --- Authorization helpers ---
def require_roles(*roles):
    """Decorator to require that the current session user has one of the given positions.

    Usage: @require_roles('chairperson','sadmin') above route handlers.
    Redirects to login if not authenticated, or to user_dashboard if unauthorized.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in first.', 'warning')
                return redirect(url_for('auth'))
            pos = (session.get('position') or '').lower()
            allowed = [r.lower() for r in roles]
            if pos not in allowed:
                flash('Access denied: insufficient permissions.', 'danger')
                return redirect(url_for('user_dashboard'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/')
def home():
    return render_template('sk_connect_homepage.html')


# - - -  - - - - -- Authenticaition ------------------------------

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        identifier = request.form['identifier']  # use a single input for username or email
        password = request.form['password']
        # next param indicates module intent (e.g., 'announcements')
        next_module = request.form.get('next') or request.args.get('next') or None

        try:
            response = supabase.table("sk_users") \
                .select("*") \
                .or_(f"username.eq.{identifier},email.eq.{identifier}") \
                .eq("password", password) \
                .execute()

            if response.data:
                user = response.data[0]
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['full_name'] = user['full_name']
                session['position'] = user['position']
                session['gender'] = user.get('gender') or ''  # Handle None case
                session['barangay'] = user.get('barangay') or ''  # Store user's barangay in session
                flash('Login successful!', 'success')
                # Isolation by position
                pos = user.get('position', '').lower()
                # If login originated from a module intent, route there after role check
                if next_module:
                    # Map module keys to admin/user routes
                    if next_module == 'announcements':
                        return redirect(url_for('admin_announcements') if pos in ['chairperson','sadmin'] else url_for('user_announcements'))
                    if next_module == 'events_project':
                        return redirect(url_for('admin_events_projects') if pos in ['chairperson','sadmin'] else url_for('user_events_projects'))
                    if next_module == 'dashboard':
                        # analytics/dashboard overview
                        if pos in ['chairperson', 'sadmin']:
                            return redirect(url_for('admin_dashboard'))
                        return redirect(url_for('user_dashboard'))
                    if next_module == 'financial_report':
                        return redirect(url_for('admin_financial_report') if pos in ['chairperson','sadmin'] else url_for('user_financial_report'))
                    if next_module == 'community_board':
                        return redirect(url_for('admin_community') if pos in ['chairperson','sadmin'] else url_for('user_community'))
                    if next_module == 'user_approval':
                        # Only admins have access to user approval; regular users go to user dashboard
                        if pos in ['chairperson', 'sadmin']:
                            return redirect(url_for('admin_user_approval'))
                        return redirect(url_for('user_dashboard'))
                    # fallback: send admins to admin area, others to user area
                    if pos in ['chairperson', 'sadmin']:
                        return redirect(url_for('admin_dashboard'))
                    return redirect(url_for('user_dashboard'))

                # fallback default redirects
                if pos in ['chairperson', 'sadmin']:
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('user_dashboard'))
            else:
                flash('Invalid username/email or password', 'danger')
        except Exception as e:
            flash(f'Login error: {e}', 'danger')

    return render_template('sk_connect_auth.html')



@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        reg = session.get('pending_registration')
        otp_input = request.form.get('otp') or (request.json and request.json.get('otp'))
        if not reg:
            return jsonify({"success": False, "error": "No pending registration found."})
        if reg['otp'] == otp_input and datetime.now(timezone.utc) < datetime.fromisoformat(reg['otp_expiry']):
            try:
                supabase.table("sk_users_pending").insert({
                    "username": reg["username"],
                    "full_name": (reg.get("full_name") or '').strip().title(),
                    "email": reg["email"],
                    "password": reg["password"],
                    "position": reg["position"],
                    "barangay": reg["barangay"],
                    "gender": reg.get("gender"),
                    "birthday": reg.get("birthday"),
                    "status": "otp_verified",
                    # Persist individual name parts (table has columns: name, Mname, Lname)
                    "name": (reg.get("first_name") or '').strip().title(),
                    "Mname": (reg.get("middle_name") or '').strip().title(),
                    "Lname": (reg.get("last_name") or '').strip().title(),
                    "created_at": datetime.utcnow().isoformat()
                }).execute()
                session.pop('pending_registration', None)
                return jsonify({"success": True})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        else:
            return jsonify({"success": False, "error": "Invalid or expired OTP."})
    return '', 204

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username')
    # Prefer explicit name parts when provided (first/middle/last). Fall back to full_name if present.
    first_name = (request.form.get('first_name') or '').strip()
    middle_name = (request.form.get('middle_name') or '').strip()
    last_name = (request.form.get('last_name') or '').strip()
    if first_name or last_name:
        parts = [first_name]
        if middle_name:
            parts.append(middle_name)
        if last_name:
            parts.append(last_name)
        full_name = ' '.join([p for p in parts if p])
        # normalize to Title Case for consistent storage
        full_name = full_name.title()
    else:
        full_name = (request.form.get('full_name') or '').strip().title()
    email = request.form.get('email')
    password = request.form.get('password')
    position = request.form.get('position')
    barangay = request.form.get('barangay')
    gender = request.form.get('gender')
    birthday = request.form.get('birthday')

    # Check if user already exists in pending or approved
    existing = supabase.table("sk_users_pending").select("id").eq("username", username).execute()
    existing_approved = supabase.table("sk_users").select("id").eq("username", username).execute()
    if existing.data or existing_approved.data:
        flash("Username already taken or pending approval.", "error")
        return redirect(url_for('auth'))

    otp = generate_otp()
    otp_expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    # Send OTP email
    if not send_otp_email(email, otp):
        flash("Failed to send OTP email. Please try again.", "error")
        return redirect(url_for('auth'))

    # Store registration data in session
    session['pending_registration'] = {
        "username": username,
        "full_name": full_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "email": email,
        "password": password,
        "position": position,
        "barangay": barangay,
        "gender": gender,
        "birthday": birthday,
        "status": "pending",
        "otp": otp,
        "otp_expiry": otp_expiry
    }
    flash("Registration submitted! Please check your email for the OTP.", "success")
    return redirect(url_for('verify_otp'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('home'))

@app.route('/admin_dashboard')
@require_roles('chairperson', 'sadmin')
def admin_dashboard():
    user = get_current_user()
    # Gather analytics counts across core tables. Best-effort queries with graceful fallback.
    def table_count(table_name):
        try:
            res = supabase.table(table_name).select("id", count="exact").execute()
            # supabase-py places the count on the response when requested
            if hasattr(res, 'count') and res.count is not None:
                return int(res.count)
            # fallback: if .data exists, use its length
            if getattr(res, 'data', None) is not None:
                return len(res.data)
        except Exception:
            pass
        return 0

    from datetime import date
    today = date.today().isoformat()

    stats = {}
    stats['announcements'] = table_count('announcements')
    stats['events_total'] = table_count('events')
    # upcoming events (date >= today)
    try:
        upcoming_res = supabase.table('events').select('id', count='exact').gte('date', today).execute()
        stats['upcoming_events'] = int(upcoming_res.count) if hasattr(upcoming_res, 'count') and upcoming_res.count is not None else (len(upcoming_res.data) if getattr(upcoming_res, 'data', None) is not None else 0)
    except Exception:
        stats['upcoming_events'] = 0

    # events with explicit status 'upcoming' (if your events table uses a status field)
    try:
        status_up_res = supabase.table('events').select('id', count='exact').ilike('status', '%upcoming%').execute()
        stats['events_status_upcoming'] = int(status_up_res.count) if hasattr(status_up_res, 'count') and status_up_res.count is not None else (len(status_up_res.data) if getattr(status_up_res, 'data', None) is not None else 0)
    except Exception:
        # fallback: try exact match
        try:
            status_up_res = supabase.table('events').select('id', count='exact').eq('status', 'upcoming').execute()
            stats['events_status_upcoming'] = int(status_up_res.count) if hasattr(status_up_res, 'count') and status_up_res.count is not None else (len(status_up_res.data) if getattr(status_up_res, 'data', None) is not None else 0)
        except Exception:
            stats['events_status_upcoming'] = 0

    stats['projects'] = table_count('projects')
    stats['users'] = table_count('sk_users')
    stats['financial_reports'] = table_count('financial_reports')
    stats['volunteer_opportunities'] = table_count('volunteer_opportunities')
    stats['volunteer_signups'] = table_count('volunteer_signups')

    # volunteers with active/approved status (not 'Pending')
    try:
        vol_active_res = supabase.table('volunteer_signups').select('id', count='exact').neq('status', 'Pending').execute()
        stats['volunteers_active'] = int(vol_active_res.count) if hasattr(vol_active_res, 'count') and vol_active_res.count is not None else (len(vol_active_res.data) if getattr(vol_active_res, 'data', None) is not None else 0)
    except Exception:
        stats['volunteers_active'] = 0

    # signups for volunteer opportunities that are upcoming (opportunity.date >= today)
    try:
        opp_res = supabase.table('volunteer_opportunities').select('id').gte('date', today).execute()
        opp_ids = [o.get('id') for o in (opp_res.data or []) if o.get('id') is not None]
        if opp_ids:
            # fetch signups whose opportunity_id is in opp_ids
            signups_res = supabase.table('volunteer_signups').select('id', count='exact').in_('opportunity_id', opp_ids).execute()
            stats['volunteers_upcoming'] = int(signups_res.count) if hasattr(signups_res, 'count') and signups_res.count is not None else (len(signups_res.data) if getattr(signups_res, 'data', None) is not None else 0)
        else:
            stats['volunteers_upcoming'] = 0
    except Exception:
        stats['volunteers_upcoming'] = 0
    stats['suggestions'] = table_count('suggestions')
    stats['polls'] = table_count('polls')
    stats['surveys'] = table_count('surveys')
    # Compute active polls: those without an end_date or with end_date >= today
    try:
        polls_res_all = supabase.table('polls').select('*').execute()
        polls_all = polls_res_all.data if getattr(polls_res_all, 'data', None) is not None else []
        active_count = 0
        for p in polls_all:
            end_date = p.get('end_date')
            if not end_date:
                active_count += 1
                continue
            try:
                # normalize and parse ISO datetime
                ed = datetime.fromisoformat(str(end_date).replace('Z', '+00:00'))
                if ed.date().isoformat() >= today:
                    active_count += 1
            except Exception:
                # if we can't parse it, count as active conservatively
                active_count += 1
        stats['polls_active'] = active_count
    except Exception:
        stats['polls_active'] = stats.get('polls', 0)
    stats['transactions_count'] = table_count('transactions')

    # total transaction amount (best-effort): fetch amounts and sum in Python
    try:
        tx_res = supabase.table('transactions').select('amount').execute()
        if getattr(tx_res, 'data', None):
            total_amount = 0.0
            for r in tx_res.data:
                try:
                    amt = float(r.get('amount') or 0)
                except Exception:
                    amt = 0.0
                total_amount += amt
            stats['transactions_total'] = total_amount
        else:
            stats['transactions_total'] = 0.0
    except Exception:
        stats['transactions_total'] = 0.0

    # Keep backward-compatible variable used elsewhere
    total_announcements = stats.get('announcements', 0)

    # pending user approvals (from sk_users_pending where status is 'pending' or null)
    try:
        pend_res = supabase.table('sk_users_pending').select('id', count='exact').or_("status.eq.pending,status.is.null").execute()
        stats['pending_approvals'] = int(pend_res.count) if hasattr(pend_res, 'count') and pend_res.count is not None else (len(pend_res.data) if getattr(pend_res, 'data', None) is not None else 0)
    except Exception:
        # fallback: try simple count
        try:
            pend_res = supabase.table('sk_users_pending').select('id', count='exact').eq('status', 'pending').execute()
            stats['pending_approvals'] = int(pend_res.count) if hasattr(pend_res, 'count') and pend_res.count is not None else (len(pend_res.data) if getattr(pend_res, 'data', None) is not None else 0)
        except Exception:
            stats['pending_approvals'] = 0

    # Also report total pending rows in sk_users_pending (useful for bookkeeping)
    try:
        total_res = supabase.table('sk_users_pending').select('id', count='exact').execute()
        if getattr(total_res, 'count', None) is not None:
            stats['sk_users_pending_rows'] = int(total_res.count)
        else:
            stats['sk_users_pending_rows'] = len(total_res.data) if getattr(total_res, 'data', None) is not None else 0
    except Exception:
        stats['sk_users_pending_rows'] = stats.get('pending_approvals', 0)

    # --- Additional dashboard counts ---
    try:
        # Events needing attendance upload: consider past or today events with enable_qr=true and zero attendance records
        need_count = 0
        try:
            ev_res = supabase.table('events').select('id,date,enable_qr').lte('date', today).eq('enable_qr', True).execute()
            events_list = ev_res.data if getattr(ev_res, 'data', None) is not None else []
            for ev in events_list:
                ev_id = ev.get('id')
                if not ev_id:
                    continue
                att_res = supabase.table('attendances').select('id', count='exact').eq('event_id', ev_id).execute()
                att_count = int(att_res.count) if hasattr(att_res, 'count') and att_res.count is not None else (len(att_res.data) if getattr(att_res, 'data', None) is not None else 0)
                if att_count == 0:
                    need_count += 1
        except Exception:
            need_count = 0
        stats['events_needing_attendance'] = need_count
    except Exception:
        stats['events_needing_attendance'] = 0

    try:
        # Financial reports due this week: look for a `due_date` column between today and 7 days from now
        week_later = (date.today() + timedelta(days=7)).isoformat()
        try:
            fr_res = supabase.table('financial_reports').select('id', count='exact').gte('due_date', today).lte('due_date', week_later).execute()
            if getattr(fr_res, 'count', None) is not None:
                stats['financial_reports_due'] = int(fr_res.count)
            else:
                stats['financial_reports_due'] = len(fr_res.data) if getattr(fr_res, 'data', None) is not None else 0
        except Exception:
            # If `due_date` doesn't exist or query fails, fallback to zero
            stats['financial_reports_due'] = 0
    except Exception:
        stats['financial_reports_due'] = 0

    try:
        # Feedback to review: count suggestions (or feedback) with pending status
        try:
            fb_res = supabase.table('suggestions').select('id', count='exact').or_("status.eq.pending,status.is.null").execute()
            if getattr(fb_res, 'count', None) is not None:
                stats['feedback_to_review'] = int(fb_res.count)
            else:
                stats['feedback_to_review'] = len(fb_res.data) if getattr(fb_res, 'data', None) is not None else 0
        except Exception:
            # fallback: try 'feedback' table if 'suggestions' doesn't match your schema
            try:
                fb_res2 = supabase.table('feedback').select('id', count='exact').or_("status.eq.pending,status.is.null").execute()
                stats['feedback_to_review'] = int(fb_res2.count) if getattr(fb_res2, 'count', None) is not None else (len(fb_res2.data) if getattr(fb_res2, 'data', None) is not None else 0)
            except Exception:
                stats['feedback_to_review'] = 0
    except Exception:
        stats['feedback_to_review'] = 0

    # Fetch recent announcements (latest 5)
    try:
        ann_res = supabase.table('announcements').select('*').order('created_at', desc=True).limit(5).execute()
        recent_announcements = ann_res.data if getattr(ann_res, 'data', None) is not None else []
    except Exception:
        recent_announcements = []

    # Fetch upcoming events (date >= today) limited to 5, ordered soonest first
    try:
        up_ev_res = supabase.table('events').select('*').gte('date', today).order('date', desc=False).limit(5).execute()
        upcoming_events_list = up_ev_res.data if getattr(up_ev_res, 'data', None) is not None else []
    except Exception:
        upcoming_events_list = []

    # Fetch active polls for dashboard (reuse logic similar to api_active_polls)
    try:
        polls_res = supabase.table('polls').select('*').order('created_at', desc=True).execute()
        polls_all = polls_res.data if getattr(polls_res, 'data', None) is not None else []
        active_polls = []
        now = datetime.utcnow()
        for p in polls_all:
            options = p.get('options') or []
            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except Exception:
                    options = []
            votes = p.get('votes') or {}
            total_votes = p.get('total_votes') or 0
            end_date = p.get('end_date')
            ended = False
            if end_date:
                try:
                    edt = datetime.fromisoformat(str(end_date).replace('Z', '+00:00'))
                    if edt < now:
                        ended = True
                except Exception:
                    pass
            if not ended:
                active_polls.append({
                    'id': p.get('id'),
                    'question': p.get('question'),
                    'options': options,
                    'votes': votes,
                    'total_votes': total_votes,
                    'end_date': end_date
                })
    except Exception:
        active_polls = []

    return render_template(
        'sk_connect_dashboard.html',
        stats=stats,
        total_announcements=total_announcements,
        recent_announcements=recent_announcements,
        upcoming_events_list=upcoming_events_list,
        active_polls=active_polls,
        full_name=(user or {}).get('full_name', 'User'),
        user=user
    )


@app.route('/forgot', methods=['POST'])
def forgot_password():
    data = request.get_json()
    identifier = data.get('identifier')
    # Find user by username or email
    user_res = supabase.table("sk_users").select("*").or_(f"username.eq.{identifier},email.eq.{identifier}").execute()
    if not user_res.data:
        # Always return success to avoid account enumeration
        return jsonify({"success": True})
    user = user_res.data[0]
    otp = generate_otp()
    otp_expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    # Save OTP and expiry to user record (or a separate table)
    supabase.table("sk_users").update({"reset_otp": otp, "reset_otp_expiry": otp_expiry}).eq("id", user["id"]).execute()
    send_otp_email(user["email"], otp)
    return jsonify({"success": True})

@app.route('/verify_forgot_otp', methods=['POST'])
def verify_forgot_otp():
    data = request.get_json()
    identifier = data.get('identifier')
    otp = data.get('otp')
    user_res = supabase.table("sk_users").select("*").or_(f"username.eq.{identifier},email.eq.{identifier}").execute()
    if not user_res.data:
        return jsonify({"success": False, "error": "User not found."})
    user = user_res.data[0]
    # Parse expiry as UTC
    expiry_str = user.get("reset_otp_expiry")
    if expiry_str:
        expiry_dt = datetime.fromisoformat(expiry_str)
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
    else:
        expiry_dt = None

    if (
        user.get("reset_otp") == otp and
        expiry_dt and
        datetime.now(timezone.utc) < expiry_dt
    ):
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Invalid or expired OTP."})
    

@app.route('/reset_password', methods=['POST'])
def reset_password():
    data = request.get_json()
    identifier = data.get('identifier')
    otp = data.get('otp')
    new_password = data.get('new_password')
    user_res = supabase.table("sk_users").select("*").or_(f"username.eq.{identifier},email.eq.{identifier}").execute()
    if not user_res.data:
        return jsonify({"success": False, "error": "User not found."})
    user = user_res.data[0]
    expiry_str = user.get("reset_otp_expiry")
    if expiry_str:
        expiry_dt = datetime.fromisoformat(expiry_str)
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
    else:
        expiry_dt = None

    if (
        user.get("reset_otp") == otp and
        expiry_dt and
        datetime.now(timezone.utc) < expiry_dt
    ):
        # Update password and clear OTP fields
        supabase.table("sk_users").update({
            "password": new_password,
            "reset_otp": None,
            "reset_otp_expiry": None
        }).eq("id", user["id"]).execute()
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Invalid or expired OTP."})
    









# --- Repeat pattern for your other admin pages ---
@app.route('/admin_community')
def admin_community():
    page = int(request.args.get('page', 1))

    # --- Add this block to fetch suggestions ---
    suggestions_res = supabase.table("suggestions").select("*").order("created_at", desc=True).execute()
    suggestions = suggestions_res.data if suggestions_res.data else []
    # Add time_ago for each suggestion
    for s in suggestions:
        s['time_ago'] = time_ago(s['created_at'])
        s['comments'] = []  # If you want to support comments later
    return render_template(
        "sk_connect_community_board.html",
        
        suggestions=suggestions,
        page=page,
      
    )

@app.route('/admin_feedback')
def admin_feedback():
    page = int(request.args.get('page', 1))
    # Fetch polls and split into active vs ended
    polls_res = supabase.table("polls").select("*").order("created_at", desc=True).execute()
    all_polls = polls_res.data if getattr(polls_res, 'data', None) is not None else []
    polls = []
    ended_polls = []
    for p in all_polls:
        # Determine if poll has ended based on end_date
        end_date = p.get('end_date')
        ended = False
        if end_date:
            try:
                ed = datetime.fromisoformat(str(end_date).replace('Z', '+00:00'))
                if ed.tzinfo is None:
                    ed = ed.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > ed:
                    ended = True
            except Exception:
                # if parse fails, assume active
                ended = False
        if ended:
            ended_polls.append(p)
        else:
            polls.append(p)

    surveys_res = supabase.table("surveys").select("*").order("created_at", desc=True).execute()
    all_surveys = surveys_res.data if surveys_res.data else []
    active_surveys = []
    ended_surveys = []
    now = datetime.now(timezone.utc)
    for s in all_surveys:
        end_date = s.get('end_date')
        ended = False
        if end_date:
            try:
                ed = datetime.fromisoformat(str(end_date).replace('Z', '+00:00'))
                if ed.tzinfo is None:
                    ed = ed.replace(tzinfo=timezone.utc)
                if now > ed:
                    ended = True
            except Exception:
                ended = False
        if ended:
            ended_surveys.append(s)
        else:
            active_surveys.append(s)

    polls_per_page = 2
    surveys_per_page = 2
    poll_start = (page - 1) * polls_per_page
    poll_end = poll_start + polls_per_page
    survey_start = (page - 1) * surveys_per_page
    survey_end = survey_start + surveys_per_page
    total_pages = max(
        (len(polls) + polls_per_page - 1) // polls_per_page,
        (len(active_surveys) + surveys_per_page - 1) // surveys_per_page
    )
    return render_template(
        "sk_connect_feedback.html",
        polls=polls[poll_start:poll_end],
        surveys=active_surveys[survey_start:survey_end],
        ended_polls=ended_polls,
        ended_surveys=ended_surveys,
        page=page,
        total_pages=total_pages
    )




#.  



@app.route('/admin_documents')
def admin_documents():
    if 'user_id' not in session:
        return redirect(url_for('auth'))
    user = get_current_user()
    
    # Fetch all documents from the unified documents table
    try:
        response = supabase.table("documents").select("*").order("created_at", desc=True).execute()
        documents = response.data if response.data else []
    except Exception as e:
        documents = []
        print(f"Error fetching documents: {e}")
    
    return render_template('sk_connect_document_management.html', 
                         full_name=get_user_attribute(user, 'full_name'), 
                         documents=documents)

@app.route('/api/documents', methods=['GET'])
def api_get_documents():
    """Fetch all documents and templates from Supabase"""
    try:
        is_template = request.args.get('is_template', 'false').lower() == 'true'
        response = supabase.table("documents").select("*").eq("is_template", is_template).order("created_at", desc=True).execute()
        documents = response.data if response.data else []
        return jsonify(documents)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/upload_document', methods=['POST'])
def upload_document():
    """Upload a document to the server and store metadata in Supabase"""
    try:
        title = request.form.get('title')
        description = request.form.get('description')
        is_template = request.form.get('is_template', 'false').lower() == 'true'
        file = request.files.get('file')
        uploaded_by = session.get('user_id', 'admin')

        if not file or not file.filename or not is_allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        filename = secure_filename(file.filename or 'uploaded_file')
        # Add timestamp to avoid name collisions
        filename = f"{int(time.time())}_{filename}"
        
        # Use separate folder for documents
        documents_folder = 'static/uploads/documents'
        save_path = os.path.join(documents_folder, filename)
        os.makedirs(documents_folder, exist_ok=True)
        file.save(save_path)

        file_url = '/' + save_path

        # Store metadata in Supabase
        data = {
            "title": title,
            "description": description,
            "file_name": file.filename,
            "file_url": file_url,
            "file_type": file.content_type,
            "file_size": os.path.getsize(save_path),
            "uploaded_by": uploaded_by,
            "is_template": is_template,
        }
        supabase.table("documents").insert(data).execute()
        return jsonify({"success": True, "message": "Document uploaded successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download_document/<doc_id>')
def download_document(doc_id):
    """Download a document by ID"""
    try:
        response = supabase.table("documents").select("*").eq("id", doc_id).single().execute()
        doc = response.data if response.data else None

        if not doc:
            return "Document not found", 404

        file_url = doc.get('file_url', '')
        if not file_url:
            return "File not found", 404

        # Remove leading slash if present
        file_path = file_url.lstrip('/')

        if not os.path.exists(file_path):
            return "File not found on server", 404

        return send_file(file_path, as_attachment=True, download_name=doc.get('file_name', 'document'))
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/delete_document/<doc_id>', methods=['POST'])
def delete_document(doc_id):
    """Delete a document by ID"""
    try:
        response = supabase.table("documents").select("*").eq("id", doc_id).single().execute()
        doc = response.data if response.data else None

        if not doc:
            return jsonify({"error": "Document not found"}), 404

        file_url = doc.get('file_url', '')
        if file_url:
            file_path = file_url.lstrip('/')
            if os.path.exists(file_path):
                os.remove(file_path)

        supabase.table("documents").delete().eq("id", doc_id).execute()
        return jsonify({"success": True, "message": "Document deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin_volunteer')
def admin_volunteer():
    if 'user_id' not in session:
        return redirect(url_for('auth'))
    user = get_current_user()
    
    try:
        # Fetch volunteer opportunities from Supabase
        response = supabase.table('volunteer_opportunities').select('*').order('created_at', desc=True).execute()
        opportunities = response.data or []
        
        # Format dates for display and creator info
        for opp in opportunities:
            if opp.get('created_at'):
                opp['created_at_display'] = datetime.fromisoformat(opp['created_at'].replace('Z', '+00:00')).strftime('%b %d, %Y')
            if opp.get('date'):
                opp['date_display'] = datetime.fromisoformat(opp['date']).strftime('%b %d, %Y')
            
            # Format creator information
            creator_name = opp.get('created_by_name', 'Unknown')
            creator_position = opp.get('created_by_position', 'Member')
            opp['created_by_display'] = f"{creator_name} ({creator_position})"
            
    except Exception as e:
        opportunities = []
        flash(f'Error loading opportunities: {str(e)}', 'error')
    
    return render_template('sk_connect_volunteer.html', 
                         full_name=get_user_attribute(user, 'full_name'),
                         user=user,
                         opportunities=opportunities)


#----------------Volunteer Opportunity Creation-----------------

@app.route('/admin_training_resources')
@require_roles('chairperson', 'sadmin')
def admin_training_resources():
    if 'user_id' not in session:
        return redirect(url_for('auth'))

    user = get_current_user()

    try:
        resp = (
            supabase
            .table('training_resources')
            .select('*')
            .order('created_at', desc=True)
            .execute()
        )
        resources = resp.data or []
    except Exception as e:
        print("Error fetching training resources:", e)
        resources = []

    return render_template(
        'sk_connect_training.html',
        full_name=get_user_attribute(user, 'full_name'),
        user=user,
        resources=resources
    )
# ---------------------------------UPLOAD----------------------------------
@app.route('/admin_training_resources/upload', methods=['POST'])
@require_roles('chairperson', 'sadmin')
def upload_training_resource():
    if 'user_id' not in session:
        return redirect(url_for('auth'))

    title    = request.form.get('title', '').strip()
    module   = request.form.get('module')
    rtype    = request.form.get('type')
    audience = request.form.get('audience')
    tags_raw = request.form.get('tags') or ''
    file     = request.files.get('file')

    if not title or not file or file.filename == '':
        flash('Please provide a title and a file.', 'warning')
        return redirect(url_for('admin_training_resources'))

    if not allowed_file(file.filename):
        flash('File type not allowed.', 'danger')
        return redirect(url_for('admin_training_resources'))

    orig_name = secure_filename(file.filename)
    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    filename = f"{ts}_{orig_name}"

    local_path = os.path.join(TRAINING_UPLOAD_FOLDER, filename)
    try:
        file.save(local_path)
    except Exception as e:
        print("Saving training file failed:", e)
        flash('Error saving file on server.', 'danger')
        return redirect(url_for('admin_training_resources'))

    file_url = url_for('static', filename=f"training/{filename}", _external=False)

    tags_list = [t.strip() for t in tags_raw.split(',') if t.strip()]

    updated_ym = datetime.utcnow().strftime('%Y-%m')

    try:
        payload = {
            "title": title,
            "module": module,
            "type": rtype,
            "audience": audience,
            "tags": tags_list,      # jsonb sa Supabase
            "length_min": 0,
            "updated": updated_ym,
            "url": file_url,
            "archived": False,      # default
        }
        res = supabase.table("training_resources").insert(payload).execute()
        print("Supabase insert result:", res)
        flash('Training resource uploaded successfully.', 'success')
    except Exception as e:
        print("Error inserting training resource:", e)
        flash('File saved locally but database insert failed.', 'danger')

    return redirect(url_for('admin_training_resources'))


# ----------------------------------ARCHIVE---------------------------------
@app.route('/admin_training_resources/archive', methods=['POST'])
@require_roles('chairperson', 'sadmin')
def archive_training_resources():
    if 'user_id' not in session:
        return jsonify(success=False, error="Not logged in"), 401

    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    action = data.get('action', 'archive')   # <-- galing sa JS: 'archive' or 'unarchive'

    if not ids:
        return jsonify(success=False, error="No ids provided"), 400

    # kung unarchive → archived = False, else archived = True
    archived_value = False if action == 'unarchive' else True

    try:
        res = (
            supabase
            .table('training_resources')
            .update({"archived": archived_value})
            .in_('id', ids)
            .execute()
        )
        updated = len(res.data or [])
        return jsonify(success=True, updated=updated)
    except Exception as e:
        print("Archive/unarchive error:", e)
        return jsonify(success=False, error=str(e)), 500


# ----------------------------------RESTORE---------------------------------

@app.route('/admin_training_resources/restore', methods=['POST'])
@require_roles('chairperson', 'sadmin')
def restore_training_resources():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.get_json() or {}
    ids = data.get('ids', [])

    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400

    try:
        res = (
            supabase.table('training_resources')
            .update({"archived": False})
            .in_('id', ids)
            .execute()
        )
        return jsonify({"success": True, "updated": len(res.data or [])})
    except Exception as e:
        print("Error restoring training resources:", e)
        return jsonify({"success": False, "error": "Restore failed"}), 500

#------------------------------YOUTH WARNINGGG ADMIN--------------------------

def is_admin(user=None):
    """
    Returns True if current user (or passed user dict) is an admin.
    """
    if user is None:
        # fallback: kunin mula sa session helper mo
        try:
            user = get_current_user()
        except Exception:
            user = None

    if not user:
        return False

    pos = (user.get('position') or '').lower()
    return pos in ['chairperson', 'sadmin']

@app.route('/admin_incidents')
def admin_incidents():
    # Require login
    if 'user_id' not in session:
        # optional: para after login, balik sa incidents
        return redirect(url_for('auth', next='incidents'))

    user = get_current_user()
    if not is_admin(user):
        flash('Admin access only.', 'danger')
        return redirect(url_for('user_dashboard'))

    # kung may helper ka na get_user_attribute, ok;
    # kung wala, pwede mo palitan to ng: full_name = user.get('full_name', '')
    full_name = get_user_attribute(user, 'full_name') if user else ''

    # Ito yung HTML template mo for admin warnings page
    return render_template('sk_connect_incident.html', full_name=full_name)


@app.route('/api/youth-warnings', methods=['GET'])
def api_get_youth_warnings():
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    user = get_current_user()
    if not is_admin(user):
        return jsonify({'error': 'forbidden'}), 403

    # base query
    query = (
        supabase
        .table('youth_warnings')
        .select('*')
        .order('occurred_at', desc=True)
    )

    # optional filters from query string
    barangay = request.args.get('barangay')
    vtype    = request.args.get('type')
    level    = request.args.get('level')
    search   = request.args.get('q')

    if barangay:
        query = query.eq('barangay', barangay)
    if vtype:
        query = query.eq('violation_type', vtype)
    if level:
        query = query.eq('warning_level', level)
    if search:
        like = f"%{search}%"
        # search across name + details + action
        query = query.or_(
            f"youth_name.ilike.{like},"
            f"details.ilike.{like},"
            f"action_taken.ilike.{like},"
            f"logged_by.ilike.{like}"
        )

    resp = query.execute()
    data = resp.data or []
    return jsonify(data)


@app.route('/api/youth-warnings', methods=['POST'])
def api_create_youth_warning():
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    user = get_current_user()
    if not is_admin(user):
        return jsonify({'error': 'forbidden'}), 403

    payload = request.get_json() or {}

    required = [
        'youth_name', 'barangay', 'violation_type',
        'warning_level', 'occurred_at', 'logged_by'
    ]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({'error': f'Missing field(s): {", ".join(missing)}'}), 400

    # handle numeric fields safely
    def to_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    row = {
        'youth_name': payload['youth_name'],
        'barangay': payload['barangay'],
        'violation_type': payload['violation_type'],
        'warning_level': payload['warning_level'],
        'occurred_at': payload['occurred_at'],  # ISO string ok for timestamptz
        'logged_by': payload['logged_by'],

        'details': payload.get('details') or '',
        'action_taken': payload.get('action_taken') or '',
        'consequence_type': payload.get('consequence_type') or 'Community Service',
        'service_days_required': to_int(payload.get('service_days_required'), 0),
        'service_days_completed': to_int(payload.get('service_days_completed'), 0),
        'linked_user_id': payload.get('linked_user_id') or None,

        # optional: visible_to_user, default true sa DB
        # 'visible_to_user': True,
        'created_at': datetime.utcnow().isoformat(),
    }

    resp = supabase.table('youth_warnings').insert(row).execute()
    if not resp.data:
        return jsonify({'error': 'insert_failed'}), 500

    return jsonify(resp.data[0]), 201


@app.route('/api/youth-warnings/<warning_id>', methods=['PATCH'])
def api_update_youth_warning(warning_id):
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    user = get_current_user()
    # admin lang muna
    if not is_admin(user):
        return jsonify({'error': 'forbidden'}), 403

    payload = request.get_json() or {}

    # fields pwede i-edit
    allowed_fields = [
        'youth_name', 'barangay', 'violation_type', 'warning_level',
        'occurred_at', 'logged_by', 'details', 'action_taken',
        'consequence_type', 'service_days_required',
        'service_days_completed', 'linked_user_id'
    ]

    update_data = {}

    # safely handle numeric fields
    if 'service_days_required' in payload:
        try:
            update_data['service_days_required'] = int(payload['service_days_required'])
        except (TypeError, ValueError):
            return jsonify({'error': 'service_days_required must be integer'}), 400

    if 'service_days_completed' in payload:
        try:
            update_data['service_days_completed'] = int(payload['service_days_completed'])
        except (TypeError, ValueError):
            return jsonify({'error': 'service_days_completed must be integer'}), 400

    # copy other fields as-is
    for field in allowed_fields:
        if field in payload and field not in update_data:
            update_data[field] = payload[field]

    if not update_data:
        return jsonify({'error': 'nothing_to_update'}), 400

    update_data['updated_at'] = datetime.utcnow().isoformat()

    resp = (
        supabase.table('youth_warnings')
        .update(update_data)
        .eq('id', warning_id)
        .execute()
    )

    if not resp.data:
        return jsonify({'error': 'not_found'}), 404

    return jsonify(resp.data[0])

@app.route('/api/youth-warnings/<warning_id>', methods=['DELETE'])
def api_delete_youth_warning(warning_id):
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    user = get_current_user()
    if not is_admin(user):
        return jsonify({'error': 'forbidden'}), 403

    resp = (
        supabase.table('youth_warnings')
        .delete()
        .eq('id', warning_id)
        .execute()
    )

    # resp.data usually contains deleted row if there was one
    return jsonify({'ok': True})

@app.route('/api/update_case', methods=['POST'])
def update_case():
    try:
        data = request.get_json() or {}
        case_id = data.get('id')
        status = data.get('status')
        days_in_process = data.get('days_in_process')

        if not case_id:
            return jsonify(success=False, error="Missing case ID"), 400

        # Convert safely
        try:
            days_value = int(days_in_process) if days_in_process is not None else None
        except ValueError:
            return jsonify(success=False, error="Days in process must be a number"), 400

        update_data = {}
        if status is not None:
            update_data['status'] = status
        if days_value is not None:
            update_data['days_in_process'] = days_value

        # 🔥 Supabase update
        response = supabase.table("cases").update(update_data).eq("id", case_id).execute()

        if not response.data:
            return jsonify(success=False, error="Case not found"), 404

        return jsonify(success=True)

    except Exception as e:
        print("UPDATE ERROR:", e)
        return jsonify(success=False, error="Server error while updating"), 500

# --- Announcements (Supabase version) ---

@app.route('/admin_announcements')
def admin_announcements():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))
    user = get_current_user()

    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 6
    start = (page - 1) * per_page

    # Sorting
    sort = request.args.get('sort', 'newest')
    order_by = 'created_at'
    desc = True
    if sort == 'oldest':
        desc = False
    elif sort == 'alphabetical':
        order_by = 'title'
        desc = False

    # Filtering
    filter_type = request.args.get('type', 'all')

    query = supabase.table("announcements").select("*")
    if filter_type != 'all':
        query = query.eq('type', filter_type)
    query = query.order(order_by, desc=desc)
    response = query.range(start, start + per_page - 1).execute()
    announcements = response.data if response.data else []

    # Get total count for KPI
    count_response = supabase.table("announcements").select("id", count="exact").execute()  # type: ignore
    total_announcements = count_response.count if hasattr(count_response, 'count') and count_response.count else len(announcements)
    # Get total count for pagination (with filter)
    count_query = supabase.table("announcements").select("id", count="exact")  # type: ignore
    if filter_type != 'all':
        count_query = count_query.eq('type', filter_type)
    count_response = count_query.execute()  # type: ignore
    total = count_response.count if hasattr(count_response, 'count') and count_response.count else len(announcements)
    total_pages = (total + per_page - 1) // per_page

    # Count pending scheduled announcements for KPI display
    try:
        scheduled_count_resp = supabase.table('scheduled_announcements').select('id', count='exact').eq('schedule_post', True).eq('processed', False).execute()  # type: ignore
        scheduled_count = scheduled_count_resp.count if hasattr(scheduled_count_resp, 'count') and scheduled_count_resp.count is not None else 0
    except Exception:
        scheduled_count = 0

    return render_template(
        'sk_connect_announcements.html',
        full_name=get_user_attribute(user, 'full_name'),
        announcements=announcements,
        page=page,
        total_pages=total_pages,
        sort=sort,
        filter_type=filter_type,
        time_ago=time_ago,
        total_announcements=total_announcements,
        scheduled_count=scheduled_count
    )

@app.route('/create_announcement', methods=['POST'])
def create_announcement():
    # Determine if this request expects JSON (AJAX) so we can return structured errors
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

    # Log incoming form for debugging
    try:
        app.logger.info(f"Create announcement form data: {dict(request.form)}")
    except Exception:
        pass

    title = request.form.get('title')
    description = request.form.get('description')
    type_ = request.form.get('type')
    # accept either snake_case or camelCase form keys from template
    send_notification = True if (request.form.get('send_notification') or request.form.get('sendNotification')) else False
    schedule_post = True if (request.form.get('schedule_post') or request.form.get('schedulePost')) else False
    schedule_time = request.form.get('schedule_time') or request.form.get('scheduleTime')

    if schedule_post:
        if not schedule_time:
            error_message = 'Schedule time is required when Schedule post is checked.'
            if is_ajax:
                return jsonify(success=False, error=error_message), 400
            flash(error_message, 'error')
            return redirect(url_for('admin_announcements'))
        try:
            normalized = schedule_time.replace('Z', '+00:00') if isinstance(schedule_time, str) else schedule_time
            schedule_dt = datetime.fromisoformat(normalized)
            if schedule_dt.tzinfo is None:
                schedule_dt = schedule_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
            schedule_time = schedule_dt.astimezone(timezone.utc).isoformat()
        except Exception:
            error_message = 'Invalid schedule time format. Please choose a valid date and time.'
            if is_ajax:
                return jsonify(success=False, error=error_message), 400
            flash(error_message, 'error')
            return redirect(url_for('admin_announcements'))
    else:
        schedule_time = None

    data = {
        "title": title,
        "description": description,
        "type": type_,
        "created_at": datetime.utcnow().isoformat(),
        "send_notification": send_notification,
        "schedule_post": schedule_post,
        "schedule_time": schedule_time,
        "views": 0,
        "notifications_sent": 0,
        "scheduled_sent": False
    }

    # Use a resilient insert helper that strips columns reported missing by PostgREST (PGRST204)
    def insert_with_schema_fallback(table_name, payload):
        payload = dict(payload)
        attempts = 0
        while True:
            attempts += 1
            try:
                return supabase.table(table_name).insert(payload).execute()
            except Exception as err:
                msg = str(err)
                # Look for PostgREST schema cache missing column message
                m = re.search(r"Could not find the '([^']+)' column", msg)
                if not m:
                    # not a missing-column error, re-raise
                    raise
                col = m.group(1)
                # if the column exists in our payload, remove and retry; otherwise re-raise
                if col in payload:
                    app.logger.warning(f"Removing missing column from payload and retrying insert: {col}")
                    payload.pop(col, None)
                    if attempts >= 10:
                        raise
                    continue
                else:
                    raise

    try:
        if schedule_post:
            res = insert_with_schema_fallback("scheduled_announcements", data)
        else:
            res = insert_with_schema_fallback("announcements", data)
        try:
            app.logger.info(f"Supabase insert response: {getattr(res, 'data', None)} status={getattr(res, 'status_code', None)}")
        except Exception:
            pass
        try:
            app.logger.info(f"Supabase insert response: {getattr(res, 'data', None)} status={getattr(res, 'status_code', None)}")
        except Exception:
            pass
        # get created announcement id if available
        created = None
        try:
            created = res.data[0] if getattr(res, 'data', None) else None
        except Exception:
            created = None
        notification_message = None
        if schedule_post:
            flash('Announcement scheduled successfully!', 'success')
            notification_message = f'Announcement scheduled for {schedule_time} and will post when the time arrives.'
        else:
            flash('Announcement published successfully!', 'success')
            # If immediate notification requested, send now (email-only)
            if send_notification:
                try:
                    # fetch all approved users' email addresses from sk_users
                    users_resp = supabase.table('sk_users').select('id,email').execute()
                    users = users_resp.data if getattr(users_resp, 'data', None) is not None else []
                    emails = [u.get('email') for u in users if u.get('email')]
                    if emails:
                        send_result = send_email_stub(emails, title, description)
                        if send_result.get('success'):
                            notification_message = f"Emails sent to {send_result['sent']} users."
                        elif send_result.get('stub'):
                            notification_message = (
                                "Announcement published, but email sending is not configured. "
                                f"SMTP host={send_result.get('smtp_host')} user={send_result.get('smtp_user')}"
                            )
                        else:
                            first_errors = ', '.join(
                                f"{f['email']}: {f['error']}" for f in send_result.get('failed', [])[:3]
                            )
                            notification_message = (
                                f"Announcement published, but email sending failed for {len(send_result.get('failed', []))} recipient(s). "
                                f"First errors: {first_errors}"
                            )
                    else:
                        notification_message = 'No user emails were found to send.'
                    # update notifications_sent count for the announcement
                    try:
                        supabase.table('announcements').update({'notifications_sent': len(emails), 'scheduled_sent': True}).eq('id', created.get('id') if created else None).execute()
                    except Exception:
                        pass
                except Exception as e:
                    app.logger.error(f"Error sending immediate announcement notifications: {e}")
                    notification_message = f'Announcement published, but email notification failed: {e}'
        if notification_message:
            flash(notification_message, 'info' if notification_message.startswith('Emails sent') else 'warning')
        # If this was an AJAX request, return JSON success payload so client can show notification
        if is_ajax:
            return jsonify({
                'success': True,
                'created': created,
                'message': 'Announcement published successfully.'
            })
    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error(f"Supabase insert error: {e}\n{tb}")
        # If AJAX, return JSON with error and short traceback
        if is_ajax:
            return jsonify({'success': False, 'error': str(e), 'trace': tb}), 500
        # non-AJAX fallback: flash and redirect
        flash(f'Error publishing announcement: {e}', 'danger')

    return redirect(url_for('admin_announcements'))


@app.route('/announcement/<int:ann_id>/view', methods=['POST'])
def announcement_view(ann_id):
    """Increment the view count for an announcement.
    Frontend should POST to this endpoint when a user clicks / opens an announcement.
    """
    try:
        # fetch current views
        res = supabase.table('announcements').select('views').eq('id', ann_id).limit(1).execute()
        cur = 0
        if getattr(res, 'data', None):
            row = res.data[0]
            cur = int(row.get('views') or 0)
        new = cur + 1
        supabase.table('announcements').update({'views': new}).eq('id', ann_id).execute()
        return jsonify({'success': True, 'views': new})
    except Exception as e:
        app.logger.error(f'Error incrementing announcement views: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/announcements/resend/<int:ann_id>', methods=['POST'])
@require_roles('chairpersons', 'skfed')
def admin_resend_announcement(ann_id):
    """Admin endpoint to resend an existing announcement to all users' emails.
    Restricted to users whose `position` is 'chairpersons' or 'skfed'.
    Returns JSON when called via AJAX, otherwise redirects back with flash messages.
    """
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    if 'user_id' not in session:
        if is_ajax:
            return jsonify({'success': False, 'error': 'not authorized'}), 403
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))

    try:
        # fetch the announcement
        resp = supabase.table('announcements').select('*').eq('id', ann_id).limit(1).execute()
        ann = resp.data[0] if getattr(resp, 'data', None) else None
        if not ann:
            msg = 'Announcement not found.'
            app.logger.warning(f'Resend failed: announcement {ann_id} not found')
            if is_ajax:
                return jsonify({'success': False, 'error': msg}), 404
            flash(msg, 'danger')
            return redirect(url_for('admin_announcements'))

        # fetch users and collect emails
        users_resp = supabase.table('sk_users').select('id,email').execute()
        users = users_resp.data if getattr(users_resp, 'data', None) is not None else []
        emails = [u.get('email') for u in users if u.get('email')]

        if not emails:
            msg = 'No user emails found to send.'
            app.logger.info('Resend aborted: no emails')
            if is_ajax:
                return jsonify({'success': False, 'error': msg}), 200
            flash(msg, 'warning')
            return redirect(url_for('admin_announcements'))

        # send emails (uses send_email_stub which respects SMTP env vars)
        try:
            send_result = send_email_stub(emails, ann.get('title') or 'Announcement', ann.get('description') or '')
            if send_result['success']:
                success_msg = f'Resent announcement to {send_result['sent']} users.'
                app.logger.info(success_msg)
                if is_ajax:
                    return jsonify({'success': True, 'message': success_msg, 'sent_count': send_result['sent']}), 200
                flash(success_msg, 'success')
            elif send_result['stub']:
                success_msg = 'Email resend did not send actual messages because SMTP is not configured.'
                app.logger.info(success_msg)
                if is_ajax:
                    return jsonify({'success': True, 'message': success_msg, 'sent_count': 0, 'stub': True}), 200
                flash(success_msg, 'warning')
            else:
                error_count = len(send_result['failed'])
                msg = f'Email resend completed with {send_result['sent']} sent and {error_count} failures. Check logs for details.'
                app.logger.warning(msg)
                if is_ajax:
                    return jsonify({'success': True, 'message': msg, 'sent_count': send_result['sent'], 'failed': send_result['failed']}), 200
                flash(msg, 'warning')
        except Exception as e:
            app.logger.error(f'Error sending announcement emails: {e}')
            if is_ajax:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(f'Error sending emails: {e}', 'danger')
            return redirect(url_for('admin_announcements'))

        # update notifications_sent counter on announcement (best-effort)
        try:
            supabase.table('announcements').update({'notifications_sent': len(emails), 'scheduled_sent': True}).eq('id', ann_id).execute()
        except Exception as e:
            app.logger.warning(f'Could not update notifications_sent for announcement {ann_id}: {e}')

        return redirect(url_for('admin_announcements'))

    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error(f'Unexpected error resending announcement {ann_id}: {e}\n{tb}')
        if is_ajax:
            return jsonify({'success': False, 'error': str(e), 'trace': tb}), 500
        flash(f'Error resending announcement: {e}', 'danger')
        return redirect(url_for('admin_announcements'))


# Web push subscription endpoints removed — using email-only notifications now.


@app.route('/admin_sms_logs')
def admin_sms_logs():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))
    user = get_current_user()
    # fetch recent sms logs
    try:
        resp = supabase.table('sms_send_logs').select('*').order('sent_at', desc=True).limit(200).execute()
        logs = resp.data if getattr(resp, 'data', None) is not None else []
    except Exception as e:
        app.logger.error(f"Could not fetch sms_send_logs: {e}")
        logs = []
    return render_template('sms_send_logs.html', full_name=get_user_attribute(user, 'full_name'), logs=logs)


@app.route('/admin_sms_logs/retry/<int:log_id>', methods=['POST'])
def admin_sms_logs_retry(log_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error':'not authorized'}), 403
    try:
        resp = supabase.table('sms_send_logs').select('*').eq('id', log_id).limit(1).execute()
        row = resp.data[0] if getattr(resp, 'data', None) else None
        if not row:
            return jsonify({'success': False, 'error': 'log not found'}), 404
        phone = row.get('phone')
        body = row.get('body') or ''
        # attempt resend
        result = send_single_sms(phone, body)
        # update log entry with new status / message_sid / error and last_attempt
        update = {
            'status': result.get('status'),
            'message_sid': result.get('message_sid'),
            'error': result.get('error'),
            'last_attempt_at': datetime.utcnow().isoformat()
        }
        supabase.table('sms_send_logs').update(update).eq('id', log_id).execute()
        return jsonify({'success': True, 'result': update})
    except Exception as e:
        app.logger.error(f"Retry send error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



#-----------------------------create eventssssssssss projectsssssssssssss

@app.route('/admin_events_projects')
def admin_events_projects():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))
    user = get_current_user()
    response = supabase.table("events").select("*").order("date", desc=True).execute()
    events = response.data if response.data else []
    now = datetime.now().date()
    # Compute event counts
    total_events = len(events)
    upcoming_events_count = 0
    for ev in events:
        ev_date_raw = ev.get('date')
        ev_date = None
        if ev_date_raw:
            try:
                # handle ISO timestamps or plain dates
                ev_date = datetime.fromisoformat(str(ev_date_raw)).date()
            except Exception:
                try:
                    ev_date = datetime.strptime(str(ev_date_raw), '%Y-%m-%d').date()
                except Exception:
                    ev_date = None
        if ev_date and ev_date > now:
            upcoming_events_count += 1
    # Fetch total users to display in KPI
    try:
        users_resp = supabase.table('users').select('id').execute()
        users = users_resp.data if getattr(users_resp, 'data', None) is not None else []
        users_count = len(users)
    except Exception:
        users_count = 0
    return render_template(
        'sk_connect_events_projects.html',
        events=events,
        full_name=get_user_attribute(user, 'full_name'),
        today=now,
        users_count=users_count,
        total_events=total_events,
        upcoming_events_count=upcoming_events_count
    )
    

@app.route('/create_event', methods=['POST'])
def create_event():
    name = request.form.get('name')
    type_ = request.form.get('type')
    description = request.form.get('description')
    date = request.form.get('date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    location = request.form.get('location')
    max_participants = request.form.get('max_participants')
    required_items = request.form.get('required_items')
    registration_deadline = request.form.get('registration_deadline')
    budget = request.form.get('budget')
    # For file upload, handle separately if needed
    cover_image_url = request.form.get('cover_image_url')
    enable_qr = True if request.form.get('enable_qr') else False
    organizer_names = request.form.getlist('organizer_names')
    organizer_positions = request.form.getlist('organizer_positions')
    organizers = [
        {"name": n, "position": p}
        for n, p in zip(organizer_names, organizer_positions)
        if n.strip() and p.strip()
    ]
    # Generate unique QR token if QR enabled
    qr_token = None
    if enable_qr:
        qr_token = uuid.uuid4().hex[:32]
    
    data = {
        "organizers": json.dumps(organizers),
        "name": name,
        "type": type_,
        "description": description,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "max_participants": max_participants,
        "required_items": required_items,
        "registration_deadline": registration_deadline,
        "budget": budget,
        "cover_image_url": cover_image_url,
        "enable_qr": enable_qr,
        # default event barangay to creator's barangay if available
        "barangay": (session.get('barangay') if session.get('barangay') else (get_current_user() or {}).get('barangay')),
        "created_at": datetime.utcnow().isoformat()
    }

    # Only include qr_token in the insert payload if a token was generated.
    # Some deployments don't have a 'qr_token' column on 'events' and including
    # the key (even with None) causes PostgREST to error (PGRST204).
    if qr_token:
        data['qr_token'] = qr_token

    try:
        result = supabase.table("events").insert(data).execute()
        event_id = result.data[0]['id'] if result.data else None
        
        # Store token in event_qr_tokens table if event was created
        if event_id and qr_token and enable_qr:
            try:
                token_record = {
                    'event_id': event_id,
                    'qr_token': qr_token,
                    'created_at': datetime.utcnow().isoformat(),
                    'active': True
                }
                supabase.table('event_qr_tokens').insert(token_record).execute()
            except Exception as e:
                print(f"Warning: Could not store QR token: {e}")
        
        flash('Event created successfully!', 'success')
    except Exception as e:
        print("Supabase insert error:", e)
        flash(f'Error creating event: {e}', 'danger')

    return redirect(url_for('admin_events_projects'))
@app.route('/edit_event', methods=['POST'])
def edit_event():
    event_id = request.form.get('event_id')

    def clean_date(val):
        return val if val else None

    data = {
        "name": request.form.get('name'),
        "type": request.form.get('type'),
        "date": clean_date(request.form.get('date')),
        "start_time": request.form.get('start_time'),
        "end_time": request.form.get('end_time'),
        "location": request.form.get('location'),
        "max_participants": request.form.get('max_participants'),
        "description": request.form.get('description'),
        "required_items": request.form.get('required_items'),
        "registration_deadline": clean_date(request.form.get('registration_deadline')),
        "budget": request.form.get('budget'),
    }
    supabase.table("events").update(data).eq("id", event_id).execute()
    flash('Event updated successfully!', 'success')
    return redirect(url_for('admin_events_projects'))

# qr code generator

# @app.route('/mark-attendance/<event_id>', methods=['GET', 'POST'])
# def mark_attendance(event_id):
#         # Log the incoming request so we can see scanner hits in server logs
#         print(f"mark-attendance hit for event_id={event_id} from {request.remote_addr} method={request.method}")

#         user_id = session.get('user_id')

#         if request.method == 'POST':
#                 # form submission from scanner device
#                 name = request.form.get('name')
#                 email = request.form.get('email')
#                 phone = request.form.get('phone')
#                 timestamp = datetime.utcnow().isoformat()

#                 # Build attendance record
#                 record = {
#                         'event_id': event_id,
#                         'marked_at': timestamp,
#                         'name': name,
#                         'email': email,
#                         'phone': phone,
#                 }
#                 if user_id:
#                         record['user_id'] = user_id

#                 # Try inserting into 'attendances' (best-effort)
#                 db_error = None
#                 try:
#                         supabase.table('attendances').insert(record).execute()
#                         print(f"Inserted attendance record for event={event_id} name={name} email={email} from {request.remote_addr}")
#                         success = True
#                 except Exception as e:
#                         db_error = str(e)
#                         print('Attendance DB write error:', e)
#                         success = False

#                 # Return confirmation page
#                 if success:
#                         html = f"""
#                         <!doctype html>
#                         <html><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Attendance Recorded</title></head>
#                         <body style=\"font-family:system-ui,Arial;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;\">
#                                 <div style=\"max-width:520px;padding:24px;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.08);text-align:center;\">
#                                         <h2 style=\"color:#0d2a52;\">Thank you</h2>
#                                         <p>Your attendance for event <strong>{event_id}</strong> has been recorded.</p>
#                                         <p style=\"font-size:12px;color:#666;margin-top:12px;\">Marked at {timestamp}</p>
#                                 </div>
#                         </body></html>
#                         """
#                         return Response(html, mimetype='text/html')


#                 # (removed nested route definitions; module-level registration/attendance APIs are declared below)

#         # GET: show a simple mobile-friendly attendance form
#         # Pre-fill with session user info if available
#         pre_name = session.get('full_name', '') if user_id else ''
#         pre_email = session.get('username', '') if user_id else ''
#         html = f"""
#         <!doctype html>
#         <html>
#         <head>
#             <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
#             <title>Mark Attendance</title>
#             <style>body{{font-family:system-ui,Arial;margin:0;padding:0;background:#f7fafc}}.card{{max-width:640px;margin:40px auto;background:#fff;border-radius:10px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}.field{{margin-bottom:12px}}label{{display:block;font-weight:600;margin-bottom:6px}}input[type=text],input[type=email],input[type=tel]{{width:100%;padding:10px;border:1px solid #e5e7eb;border-radius:6px}}button{{background:#0d2a52;color:#fff;padding:10px 14px;border-radius:8px;border:none;font-weight:700;width:100%}}</style>
#         </head>
#         <body>
#             <div class=\"card\">
#                 <h2 style=\"color:#0d2a52;margin-top:0;\">Mark Attendance</h2>
#                 <p style=\"color:#4b5563;\">Event ID: <strong>{event_id}</strong></p>
#                 <form method=\"POST\" action=\"{request.path}\">
#                     <div class=\"field\">
#                         <label for=\"name\">Full name</label>
#                         <input id=\"name\" name=\"name\" type=\"text\" value=\"{pre_name}\" required />
#                     </div>
#                     <div class=\"field\">
#                         <label for=\"email\">Email (optional)</label>
#                         <input id=\"email\" name=\"email\" type=\"email\" value=\"{pre_email}\" />
#                     </div>
#                     <div class=\"field\">
#                         <label for=\"phone\">Phone number (optional)</label>
#                         <input id=\"phone\" name=\"phone\" type=\"tel\" />
#                     </div>
#                     <div style=\"margin-top:14px;\"> 
#                         <button type=\"submit\">Submit Attendance</button>
#                     </div>
#                 </form>
#                 <div style=\"margin-top:12px;color:#6b7280;font-size:13px;\">If you have an account, <a href=\"{url_for('auth', _external=True)}\">log in</a> first to attach this record to your account.</div>
#             </div>
#         </body>
#         </html>
#         """
#         return Response(html, mimetype='text/html')





        # ---------------Financial report --------------------------------------
@app.route('/admin_financial_report')
def admin_financial_report():
    response = supabase.table("projects").select("*").order("created_at", desc=True).limit(10).execute()
    recent_projects = response.data if response.data else []
    tx_response = supabase.table("transactions").select("*").order("date", desc=True).limit(10).execute()
    recent_transactions = tx_response.data if tx_response.data else []
    all_tx_response = supabase.table("transactions").select("*").order("date", desc=True).execute()
    all_transactions = all_tx_response.data if all_tx_response.data else []

    # Fetch financial reports
    try:
        reports_response = supabase.table("financial_reports").select("*").order("created_at", desc=True).execute()
        financial_reports = reports_response.data if reports_response.data else []
    except Exception as e:
        print(f"Error fetching financial reports: {e}")
        financial_reports = []

    # Compute totals across all projects for dashboard KPIs
    try:
        # fetch id, name, category, budget, spent, and barangay so the template can render them
        all_projects_resp = supabase.table("projects").select("id, budget_allocated, amount_spent, name, category, barangay, status, start_date").execute()
        all_projects = all_projects_resp.data if all_projects_resp.data else []
        
        # Calculate progress for each project
        for project in all_projects:
            budget = float(project.get('budget_allocated') or 0)
            spent = float(project.get('amount_spent') or 0)
            project['progress'] = round((spent / budget * 100) if budget > 0 else 0)
        
    except Exception:
        all_projects = []

    total_budget = 0.0
    total_spent = 0.0
    for p in all_projects:
        try:
            b = float(p.get('budget_allocated') or 0)
        except Exception:
            b = 0.0
        try:
            s = float(p.get('amount_spent') or 0)
        except Exception:
            s = 0.0
        total_budget += b
        total_spent += s

    remaining = max(total_budget - total_spent, 0.0)
    percent_spent = (total_spent / total_budget * 100.0) if total_budget > 0 else 0.0

    return render_template(
        'sk_connect_financial_report.html',
        recent_projects=recent_projects,
        recent_transactions=recent_transactions,
        all_transactions=all_transactions,
        total_budget=total_budget,
        total_spent=total_spent,
        remaining=remaining,
        percent_spent=percent_spent,
        all_projects=all_projects,
        financial_reports=financial_reports,
        current_user=get_current_user(),
    )


@app.route('/api/monthly_spending')
def api_monthly_spending():
    """Return monthly series for a given year and metric.

    Query params:
      - year: YYYY (defaults to current year)
      - metric: 'spent'|'allocated'|'remaining'|'projects' (defaults to 'spent')

    This endpoint is a convenience for client-side code that prefers an HTTP API.
    """
    year = request.args.get('year') or str(datetime.utcnow().year)
    metric = request.args.get('metric') or 'spent'
    labels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

    # Try transactions first (for 'spent')
    try:
        if metric == 'spent':
            tx_res = supabase.table('transactions').select('date,amount,type,barangay,project_id').execute()
            txs = tx_res.data if tx_res.data else []
            arr = [0]*12
            for tx in txs:
                try:
                    d = datetime.fromisoformat(str(tx.get('date')).replace('Z','+00:00'))
                except Exception:
                    continue
                if str(d.year) != str(year):
                    continue
                if tx.get('type') == 'income':
                    continue
                m = d.month - 1
                try:
                    amt = float(tx.get('amount') or 0)
                except Exception:
                    amt = 0
                arr[m] += abs(amt)
            return jsonify({'labels': labels, 'data': arr})

        # Fallback to projects-derived series for other metrics
        proj_res = supabase.table('projects').select('start_date,end_date,budget_allocated,amount_spent').execute()
        projects = proj_res.data if proj_res.data else []
        arr = [0]*12
        for p in projects:
            try:
                start = None
                end = None
                if p.get('start_date'):
                    start = datetime.fromisoformat(str(p.get('start_date')).split('T')[0]).month - 1
                if p.get('end_date'):
                    end = datetime.fromisoformat(str(p.get('end_date')).split('T')[0]).month - 1
            except Exception:
                start = None
                end = None
            try:
                budget = float(p.get('budget_allocated') or 0)
            except Exception:
                budget = 0
            try:
                spent = float(p.get('amount_spent') or 0)
            except Exception:
                spent = 0
            rem = budget - spent
            monthlyAlloc = budget / 12 if budget else 0
            monthlySpent = spent / 12 if spent else 0
            monthlyRem = rem / 12 if rem else 0
            if start is None or end is None or start > end:
                # if dates are missing, distribute across first half of year as a best-effort
                for m in range(6):
                    arr[m] += (monthlyAlloc if metric == 'allocated' else monthlySpent if metric == 'spent' else monthlyRem if metric == 'remaining' else 0)
            else:
                for m in range(start, end+1):
                    arr[m] += (monthlyAlloc if metric == 'allocated' else monthlySpent if metric == 'spent' else monthlyRem if metric == 'remaining' else 0)

        return jsonify({'labels': labels, 'data': arr})
    except Exception as e:
        app.logger.exception('api_monthly_spending error')
        # Return sample data on error
        sample = [120000,150000,180000,140000,200000,160000,0,0,0,0,0,0]
        return jsonify({'labels': labels, 'data': sample})


@app.route('/admin_all_transactions')
def admin_all_transactions():
    """Show a dedicated page for expense transactions with server-side pagination."""
    from datetime import datetime
    now = datetime.utcnow()
    # Basics: page and per_page params
    try:
        page = int(request.args.get('page', 1))
        if page < 1: page = 1
    except Exception:
        page = 1
    per_page = int(request.args.get('per_page', 25))
    start = (page - 1) * per_page
    end = start + per_page - 1

    # Fetch expense transactions only
    try:
        res = supabase.table('transactions').select('*').eq('type', 'expense').order('date', desc=True).range(start, end).execute()
        txs = res.data if getattr(res, 'data', None) is not None else []
    except Exception:
        txs = []

    # Attach project names to transactions for display
    try:
        proj_res = supabase.table('projects').select('id,name').execute()
        projects = proj_res.data if getattr(proj_res, 'data', None) is not None else []
        proj_map = {str(p.get('id')): p.get('name') for p in projects}
        # Add project_name to each transaction dict (if not present)
        for tx in txs:
            pid = tx.get('project_id')
            if pid is not None:
                tx['project_name'] = proj_map.get(str(pid)) or tx.get('project_id')
            else:
                tx['project_name'] = tx.get('project_id') or '—'
    except Exception:
        # If fetching projects failed, ensure key exists to avoid template errors
        for tx in txs:
            tx['project_name'] = tx.get('project_id') or '—'

    # Get total count for pagination
    try:
        count_res = supabase.table('transactions').select('id', count='exact').eq('type', 'expense').execute()
        total = int(count_res.count) if hasattr(count_res, 'count') and count_res.count is not None else (len(txs) if txs else 0)
    except Exception:
        total = len(txs)

    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1

    # Calculate statistics
    total_amount = 0
    monthly_amount = 0
    all_txs = []
    
    try:
        # Get all transactions for calculations
        all_res = supabase.table('transactions').select('*').eq('type', 'expense').execute()
        all_txs = all_res.data if getattr(all_res, 'data', None) is not None else []
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        for tx in all_txs:
            try:
                amount = float(tx.get('amount', 0))
                date_str = tx.get('date', '')
                
                # Total for all transactions
                total_amount += amount
                
                # Calculate monthly total
                if date_str:
                    try:
                        tx_date = datetime.strptime(date_str, '%Y-%m-%d')
                        if tx_date.year == current_year and tx_date.month == current_month:
                            monthly_amount += amount
                    except:
                        pass
            except:
                pass
    except Exception:
        pass

    # Calculate average amount
    avg_amount = total_amount / total if total > 0 else 0

    # Get current date for the template
    now = datetime.now()

    user = get_current_user()
    return render_template('sk_connect_all_transactions.html',
                           transactions=txs,
                           page=page,
                           per_page=per_page,
                           total=total,
                           total_pages=total_pages,
                           total_amount=total_amount,
                           monthly_amount=monthly_amount,
                           avg_amount=avg_amount,
                           full_name=(user or {}).get('full_name', ''),
                           user=user,
                           now=now)


@app.route('/upload_financial_report', methods=['POST'])
def upload_financial_report():
    title = request.form.get('title')
    report_type = request.form.get('report_type')
    description = request.form.get('description')
    file = request.files.get('file')
    uploaded_by = session.get('user_id', 'admin')  # or however you track users

    if not file or not file.filename or not is_allowed_file(file.filename):
        flash('Invalid file type.', 'danger')
        return redirect(url_for('admin_financial_report'))

    filename = secure_filename(file.filename or 'uploaded_file')
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(save_path)

    file_url = '/' + save_path  # For static serving

    data = {
        "title": title,
        "report_type": report_type,
        "description": description,
        "file_url": file_url,
        "uploaded_by": uploaded_by,
    }
    supabase.table("financial_reports").insert(data).execute()
    flash('Financial report uploaded successfully!', 'success')
    return redirect(url_for('admin_financial_report'))

@app.route('/download_financial_report/<report_id>')
def download_financial_report(report_id):
    """Download a financial report by ID"""
    try:
        # Fetch the report from database
        response = supabase.table("financial_reports").select("*").eq("id", report_id).single().execute()
        report = response.data if response.data else None
        
        if not report:
            flash('Report not found.', 'danger')
            return redirect(url_for('admin_financial_report'))
        
        file_url = report.get('file_url', '')
        if not file_url:
            flash('File not found.', 'danger')
            return redirect(url_for('admin_financial_report'))
        
        # Remove leading slash if present
        file_path = file_url.lstrip('/')
        
        # Check if file exists
        if not os.path.exists(file_path):
            flash('File not found on server.', 'danger')
            return redirect(url_for('admin_financial_report'))
        
        # Send the file
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f'Error downloading report: {str(e)}', 'danger')
        return redirect(url_for('admin_financial_report'))

@app.route('/delete_financial_report/<report_id>', methods=['POST'])
def delete_financial_report(report_id):
    """Delete a financial report by ID"""
    try:
        # Fetch the report from database
        response = supabase.table("financial_reports").select("*").eq("id", report_id).single().execute()
        report = response.data if response.data else None
        
        if not report:
            flash('Report not found.', 'danger')
            return redirect(url_for('admin_financial_report'))
        
        file_url = report.get('file_url', '')
        if file_url:
            # Remove leading slash if present
            file_path = file_url.lstrip('/')
            
            # Delete the file from storage
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Delete the record from database
        supabase.table("financial_reports").delete().eq("id", report_id).execute()
        flash('Financial report deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting report: {str(e)}', 'danger')
    
    return redirect(url_for('admin_financial_report'))

@app.route('/create_project', methods=['POST'])
def create_project():
    name = request.form.get('name')
    category = request.form.get('category')
    description = request.form.get('description')
    budget_allocated = request.form.get('budget_allocated')
    amount_spent = request.form.get('amount_spent') or 0
    start_date = request.form.get('start_date') or None
    end_date = request.form.get('end_date') or None
    project_manager = request.form.get('project_manager')
    status = request.form.get('status') or 'Ongoing'
    barangay = request.form.get('barangay') or ''  # Get barangay from form (auto-populated from user profile)

    # Debug logging
    print(f"DEBUG: Creating project with barangay: '{barangay}'")
    print(f"DEBUG: Form data - Name: {name}, Category: {category}, Barangay: {barangay}")

    data = {
        "name": name,
        "category": category,
        "description": description,
        "budget_allocated": budget_allocated if budget_allocated else 0,
        "amount_spent": amount_spent if amount_spent else 0,
        "start_date": start_date if start_date else None,
        "end_date": end_date if end_date else None,
        "project_manager": project_manager if project_manager else '',
        "status": status,
        "barangay": barangay if barangay else '',  # Include barangay in data
        "created_at": datetime.utcnow().isoformat()
    }

    print(f"DEBUG: Data to be inserted: {data}")

    try:
        result = supabase.table("projects").insert(data).execute()
        print(f"DEBUG: Project created successfully. Response: {result}")
        print(f"DEBUG: Project created with barangay: '{barangay}'")
        flash('Project created successfully!', 'success')
    except Exception as e:
        print("Supabase insert error:", e)
        print(f"DEBUG: Error details: {str(e)}")
        print(f"DEBUG: Error type: {type(e)}")
        flash(f'Error creating project: {e}', 'danger')

    return redirect(url_for('admin_financial_report'))


@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    # Accept both form-encoded and JSON payloads
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()

        project_id = data.get('project_id') or None
        title = (data.get('title') or '').strip()
        amount_raw = data.get('amount') or '0'
        try:
            amount = float(amount_raw)
        except Exception:
            amount = 0.0
        tx_type = data.get('type') or 'expense'
        category = data.get('category') or None
        # Note: enforce permissions and ensure barangay is taken from the project record
        date_val = data.get('date') or None
        description = data.get('description') or None

        user = get_current_user()

        # If not logged in, reject
        if not user:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401

        user_position = (user.get('position') or '').lower()
        user_barangay = (user.get('barangay') or '').strip()

        project_barangay = None

        # If a project_id is supplied, fetch its barangay
        if project_id:
            try:
                p_res = supabase.table('projects').select('id,barangay').eq('id', project_id).limit(1).execute()
                p_data = p_res.data if getattr(p_res, 'data', None) is not None else []
                if p_data:
                    project_barangay = (p_data[0].get('barangay') or '').strip()
                else:
                    # project not found
                    return jsonify({'success': False, 'error': 'Project not found'}), 400
            except Exception as e:
                app.logger.error(f'Error fetching project for add_transaction: {e}')
                return jsonify({'success': False, 'error': 'Failed to verify project'}), 500
        else:
            # no project specified
            project_barangay = None

        # Authorization rules:
        # - sadmin (position == 'sadmin') can add expenses for any project (and without project)
        # - other users can only add expenses when project_id is provided and their user barangay matches the project's barangay
        if user_position != 'sadmin':
            if not project_id:
                return jsonify({'success': False, 'error': 'Only system admins can add expenses without a project'}), 403
            if not project_barangay:
                return jsonify({'success': False, 'error': 'Project barangay unavailable'}), 400
            # normalize compare lowercase
            if user_barangay.lower() != project_barangay.lower():
                return jsonify({'success': False, 'error': 'You are not authorized to add expenses for this project (barangay mismatch)'}), 403

        # Ensure the expense's barangay is set to the project's barangay (if project present)
        final_barangay = project_barangay if project_barangay else (user_barangay or None)

        row = {
            'project_id': project_id,
            'title': title,
            'amount': amount,
            'type': tx_type,
            'category': category,
            'barangay': final_barangay,
            'date': date_val,
            'description': description
        }

        # Insert the transaction
        supabase.table('transactions').insert(row).execute()
        
        # If this is an expense and a project is specified, update the project's amount_spent
        if project_id and tx_type == 'expense':
            try:
                # Fetch current amount_spent
                p_res = supabase.table('projects').select('amount_spent').eq('id', project_id).limit(1).execute()
                if p_res.data:
                    current_spent = float(p_res.data[0].get('amount_spent') or 0)
                    new_spent = current_spent + amount
                    # Update project with new amount_spent
                    supabase.table('projects').update({'amount_spent': new_spent}).eq('id', project_id).execute()
            except Exception as e:
                app.logger.error(f'Error updating project amount_spent: {e}')
                # Continue anyway - transaction is already saved
        
        # Return JSON for AJAX callers
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f'add_transaction error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/edit_project', methods=['POST'])
def edit_project():
    project_id = request.form.get('project_id')
    new_spent = float(request.form.get('amount_spent') or 0)

    response = supabase.table("projects").select("amount_spent,name,category").eq("id", project_id).execute()
    prev_spent = float(response.data[0]['amount_spent']) if response.data else 0
    proj_name = response.data[0].get('name') if response.data else 'Project'
    proj_cat = response.data[0].get('category') if response.data else 'General'

    data = {
        "name": request.form.get('name'),
        "category": request.form.get('category'),
        "description": request.form.get('description'),
        "budget_allocated": request.form.get('budget_allocated'),
        "amount_spent": new_spent,
        "start_date": request.form.get('start_date'),
        "end_date": request.form.get('end_date'),
        "project_manager": request.form.get('project_manager'),
        "status": request.form.get('status'),
    }
    supabase.table("projects").update(data).eq("id", project_id).execute()

    if new_spent > prev_spent:
        spent_diff = new_spent - prev_spent
        tx_data = {
            "project_id": project_id,
            "title": f"Expense for {proj_name}",
            "amount": spent_diff,
            "type": "expense",
            "category": proj_cat,
            "date": datetime.now().date().isoformat(),
            "description": f"Recorded via project edit. Previous: ₱{prev_spent}, New: ₱{new_spent}"
        }
        supabase.table("transactions").insert(tx_data).execute()

    return '', 204

@app.route('/admin_archived_projects')
def admin_archived_projects():
    response = supabase.table("archived_projects").select("*").order("archived_at", desc=True).execute()
    archived_projects = response.data if response.data else []
    return render_template('sk_connect_archived_projects.html', archived_projects=archived_projects)

# API endpoint for fetching a single project by ID
from flask import jsonify

@app.route('/api/project/<int:project_id>')
def api_project(project_id):
    res = supabase.table("projects").select("*").eq("id", project_id).execute()
    if not res.data:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(res.data[0])

@app.route('/api/recalculate_spending', methods=['POST'])
def recalculate_spending():
    """Recalculate amount_spent for all projects based on their transactions."""
    try:
        # Fetch all projects
        projects_res = supabase.table('projects').select('id').execute()
        projects = projects_res.data if getattr(projects_res, 'data', None) is not None else []
        
        # Fetch all expense transactions
        transactions_res = supabase.table('transactions').select('project_id, amount').eq('type', 'expense').execute()
        transactions = transactions_res.data if getattr(transactions_res, 'data', None) is not None else []
        
        # Group transactions by project_id and sum amounts
        spending_map = {}
        for tx in transactions:
            proj_id = tx.get('project_id')
            if proj_id:
                amount = float(tx.get('amount') or 0)
                spending_map[proj_id] = spending_map.get(proj_id, 0) + amount
        
        # Update each project with calculated amount_spent
        updated_count = 0
        for project in projects:
            proj_id = project.get('id')
            calculated_spent = spending_map.get(proj_id, 0)
            
            try:
                supabase.table('projects').update({'amount_spent': calculated_spent}).eq('id', proj_id).execute()
                updated_count += 1
            except Exception as e:
                app.logger.error(f'Error updating project {proj_id}: {e}')
        
        return jsonify({'success': True, 'updated': updated_count, 'total_projects': len(projects)})
    except Exception as e:
        app.logger.error(f'recalculate_spending error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500



# ------------------poll and survey ----------------------------
# SQLite database setup
DATABASE = 'schema.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def get_latest_poll():
    response = supabase.table("polls").select("*").order("created_at", desc=True).limit(1).execute()
    if response.data:
        return response.data[0]
    return None

def get_latest_survey():
    response = supabase.table("surveys").select("*").order("created_at", desc=True).limit(1).execute()
    if response.data:
        return response.data[0]
    return None


@app.route('/api/survey/<int:survey_id>')
def api_survey(survey_id):
    res = supabase.table("surveys").select("*").eq("id", survey_id).execute()
    if not res.data:
        return jsonify({"error": "Survey not found"}), 404
    survey = res.data[0]
    # Ensure questions is a list
    questions = survey.get('questions')
    if isinstance(questions, str):
        questions = json.loads(questions)
    return jsonify({
        "id": survey["id"],
        "title": survey["title"],
        "description": survey["description"],
        "questions": questions or []
    })



# poll]


@app.route('/create_poll', methods=['POST'])
def create_poll():
    # Log incoming headers for debugging
    try:
        print(f"[create_poll] Headers: X-Requested-With={request.headers.get('X-Requested-With')} Cookie={'present' if request.headers.get('Cookie') else 'none'}")
        raw = (request.get_data() or b'').decode('utf-8', errors='replace')
        print(f"[create_poll] Raw body: {raw[:1000]}")
    except Exception:
        pass

    question = request.form.get('question', '').strip()
    options = [o.strip() for o in request.form.getlist('options') if o and o.strip()]
    end_date = request.form.get('end_date', '').strip()
    end_time = request.form.get('end_time', '').strip()
    combined_end = f"{end_date}T{end_time}" if end_date and end_time else end_date or None

    # Validation
    if not question:
        msg = 'Poll question is required.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": False, "error": msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('admin_feedback'))
    if len(options) < 2:
        msg = 'At least two poll options are required.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": False, "error": msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('admin_feedback'))

    data = {
        "question": question,
        "options": options,
        "votes": {},
        "total_votes": 0,
        "end_date": combined_end,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        res = supabase.table("polls").insert(data).execute()
        inserted_id = None
        if getattr(res, 'data', None):
            inserted = res.data[0]
            if isinstance(inserted, dict):
                inserted_id = inserted.get('id')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": True, "id": inserted_id}), 200
        flash('Poll created successfully!', 'success')
        return redirect(url_for('admin_feedback'))
    except Exception as e:
        print("Supabase insert error:", e)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": False, "error": str(e)}), 500
        flash(f'Error creating poll: {e}', 'danger')
        return redirect(url_for('admin_feedback'))


@app.route('/create_survey', methods=['POST'])
def create_survey():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    audience = request.form.get('audience', '').strip()
    end_date = request.form.get('end_date', '').strip()
    end_time = request.form.get('end_time', '').strip()
    combined_end = f"{end_date}T{end_time}" if end_date and end_time else end_date or None

    # Validation
    if not title:
        msg = 'Survey title is required.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": False, "error": msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('admin_feedback'))
    if not description:
        msg = 'Survey description is required.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": False, "error": msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('admin_feedback'))

    data = {
        "title": title,
        "description": description,
        "category": category if category else None,
        "audience": audience if audience else None,
        "questions": json.dumps([]),
        "total_responses": 0,
        "end_date": combined_end,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        res = supabase.table("surveys").insert(data).execute()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": True}), 200
        flash('Survey created successfully!', 'success')
        return redirect(url_for('admin_feedback'))
    except Exception as e:
        print("Supabase insert error:", e)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
            return jsonify({"success": False, "error": str(e)}), 500
        flash(f'Error creating survey: {e}', 'danger')
        return redirect(url_for('admin_feedback'))


@app.route('/submit_suggestion', methods=['POST'])
def submit_suggestion():
    title = request.form.get('title')
    category = request.form.get('category')
    description = request.form.get('description')
    author = request.form.get('author', 'Anonymous')

    bad_words = [
        'fuck', 'shit', 'bitch', 'asshole', 'bastard', 'damn', 'crap', 'piss', 'dick',
        'slut', 'whore', 'nigger', 'cunt', 'faggot', 'arse', 'bollocks', 'twat', 'wanker',
        'gago', 'tanga', 'tangina', 'tang ina', 'tangina mo', 'tarantado', 'bobo', 'ulol',
        'pekpek', 'putang ina', 'pakyu', 'pakyos', 'kupal', 'kerebol', 'leche', 'pakshet',
        'buang', 'yawa', 'bayot', 'aspal', 'bugo', 'yawa ka', 'putangina'
    ]
    profanity_pattern = re.compile(r'\b(?:' + '|'.join(re.escape(word) for word in bad_words) + r')\b', re.IGNORECASE)
    def censor(value):
        if not value:
            return value
        return profanity_pattern.sub(lambda m: '*' * len(m.group(0)), value)

    clean_title = censor(title)
    clean_description = censor(description)
    clean_author = censor(author)
    if clean_title != title or clean_description != description or clean_author != author:
        flash('Profanity was replaced with asterisks before saving your suggestion.', 'warning')

    data = {
        "title": clean_title,
        "category": category,
        "description": clean_description,
        "author": clean_author,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        supabase.table("suggestions").insert(data).execute()
        flash('Suggestion submitted successfully!', 'success')
    except Exception as e:
        print("Supabase insert error:", e)
        flash('Failed to submit suggestion.', 'danger')

    return redirect(url_for('user_community'))

@app.route('/vote_poll', methods=['POST'])
def vote_poll():
    poll_id = request.form.get('poll_id')
    option = request.form.get('option')
    user_id = session.get('user_id')

    # Check if user already voted
    vote_check = supabase.table("poll_votes").select("id").eq("poll_id", poll_id).eq("user_id", user_id).execute()
    if vote_check.data:
        return jsonify({'success': False, 'error': 'You have already voted on this poll.'}), 400

    # Record the vote
    poll_res = supabase.table("polls").select("votes, total_votes").eq("id", poll_id).execute()
    if not poll_res.data:
        return jsonify({'success': False, 'error': 'Poll not found'}), 404

    poll = poll_res.data[0]
    votes = poll.get('votes', {}) or {}
    votes[option] = votes.get(option, 0) + 1
    total_votes = poll.get('total_votes', 0) + 1

    supabase.table("polls").update({
        "votes": votes,
        "total_votes": total_votes
    }).eq("id", poll_id).execute()

    # Save user vote
    supabase.table("poll_votes").insert({
        "poll_id": poll_id,
        "user_id": user_id,
        "option": option
    }).execute()

    return jsonify({'success': True, 'votes': votes, 'total_votes': total_votes})

@app.route('/submit_survey', methods=['POST'])
def submit_survey():
    survey_id = request.form.get('survey_id')
    user_id = session.get('user_id')
    response = request.form.to_dict()
    response.pop('survey_id', None)

    supabase.table("survey_responses").insert({
        "survey_id": survey_id,
        "user_id": user_id,
        "response": response
    }).execute()

    return jsonify({'success': True})


@app.route('/api/poll_results/<int:poll_id>')
def api_poll_results(poll_id):
    """Return poll results JSON for frontend consumption."""
    try:
        res = supabase.table('polls').select('*').eq('id', poll_id).execute()
        if not res.data:
            return jsonify({'error': 'Poll not found'}), 404
        poll = res.data[0]
        # Normalize options and votes
        options = poll.get('options') or []
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except Exception:
                options = []
        votes = poll.get('votes') or {}
        total_votes = poll.get('total_votes') or 0

        return jsonify({
            'id': poll.get('id'),
            'question': poll.get('question'),
            'end_date': poll.get('end_date'),
            'options': options,
            'votes': votes,
            'total_votes': total_votes
        })
    except Exception as e:
        print('api_poll_results error:', e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/survey_results/<int:survey_id>')
def api_survey_results(survey_id):
    """Return survey results aggregated per question.

    Expected output shape used by frontend:
    {
      'id': survey_id,
      'title': ..., 'end_date': ...,
      'questions': [ { 'id': qid, 'question': text, 'type': 'single_choice'|'text', 'options': [...], 'answers': {opt:count} }, ...]
    }
    """
    try:
        sres = supabase.table('surveys').select('*').eq('id', survey_id).execute()
        if not sres.data:
            return jsonify({'error': 'Survey not found'}), 404
        survey = sres.data[0]
        questions_raw = survey.get('questions') or []
        if isinstance(questions_raw, str):
            try:
                questions = json.loads(questions_raw)
            except Exception:
                questions = []
        else:
            questions = questions_raw

        # Fetch responses for this survey
        resp_res = supabase.table('survey_responses').select('*').eq('survey_id', survey_id).execute()
        responses = resp_res.data if getattr(resp_res, 'data', None) is not None else []

        # Prepare questions structure. Support two shapes: simple list of strings or list of dicts with id/options
        qlist = []
        questions.forEach if False else None  # no-op to keep linter quiet in case of mixed shapes
        for idx, q in enumerate(questions if questions else []):
            # Normalizing question format
            if isinstance(q, str):
                qid = f"q{idx+1}"
                qtext = q
                qtype = 'text'
                qoptions = []
            elif isinstance(q, dict):
                qid = q.get('id') or f"q{idx+1}"
                qtext = q.get('question') or q.get('label') or ''
                qtype = q.get('type') or ('single_choice' if q.get('options') else 'text')
                qoptions = q.get('options') or []
            else:
                qid = f"q{idx+1}"
                qtext = str(q)
                qtype = 'text'
                qoptions = []

            # initialize counts
            answers_count = {}
            if qoptions:
                for opt in qoptions:
                    answers_count[opt] = 0

            qlist.append({ 'id': qid, 'question': qtext, 'type': qtype, 'options': qoptions, 'answers': answers_count })

        # Aggregate responses: assume response field is a dict-like mapping answer keys to values
        for r in responses:
            resp = r.get('response') or {}
            # If stored as JSON string, try parse
            if isinstance(resp, str):
                try:
                    resp = json.loads(resp)
                except Exception:
                    resp = {}
            if not isinstance(resp, dict):
                continue
            # Match keys to question entries: keys may be like 'answer_0', 'answer_1' or question ids
            for qentry in qlist:
                # Look for matching keys by index or id
                val = None
                # try id key
                if qentry['id'] in resp:
                    val = resp.get(qentry['id'])
                else:
                    # try answer_{n} pattern
                    # get numeric index from id if available
                    if qentry['id'].startswith('q') and qentry['id'][1:].isdigit():
                        ai = int(qentry['id'][1:]) - 1
                        key = f'answer_{ai}'
                        if key in resp:
                            val = resp.get(key)
                if val is None:
                    # nothing for this question in this response
                    continue
                # If multiple answers (multi-choice) are sent as list, iterate
                if isinstance(val, list):
                    for v in val:
                        qentry['answers'][v] = qentry['answers'].get(v, 0) + 1
                else:
                    # normalize to string for matching options
                    sval = str(val)
                    if qentry['options']:
                        # If option present in known options
                        if sval in qentry['answers']:
                            qentry['answers'][sval] = qentry['answers'].get(sval, 0) + 1
                        else:
                            # unknown option: record under this string
                            qentry['answers'][sval] = qentry['answers'].get(sval, 0) + 1
                    else:
                        # free text: count occurrences of answers as text keys
                        qentry['answers'][sval] = qentry['answers'].get(sval, 0) + 1

        return jsonify({
            'id': survey.get('id'),
            'title': survey.get('title'),
            'end_date': survey.get('end_date'),
            'questions': qlist
        })
    except Exception as e:
        print('api_survey_results error:', e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/active_polls')
def api_active_polls():
    """Return a list of recent active polls (not ended) for dashboard display."""
    try:
        # Get all polls ordered by created_at desc
        res = supabase.table('polls').select('*').order('created_at', desc=True).execute()
        polls_all = res.data if getattr(res, 'data', None) is not None else []
        active = []
        now = datetime.utcnow()
        for p in polls_all:
            # Normalize fields
            options = p.get('options') or []
            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except Exception:
                    options = []
            votes = p.get('votes') or {}
            total_votes = p.get('total_votes') or 0
            end_date = p.get('end_date')
            ended = False
            if end_date:
                try:
                    edt = datetime.fromisoformat(end_date.replace('Z','+00:00'))
                    if edt < now:
                        ended = True
                except Exception:
                    pass
            if not ended:
                active.append({
                    'id': p.get('id'),
                    'question': p.get('question'),
                    'options': options,
                    'votes': votes,
                    'total_votes': total_votes,
                    'end_date': end_date
                })

        # Optionally mark if current user already voted
        user_id = session.get('user_id')
        if user_id and active:
            for poll in active:
                try:
                    check = supabase.table('poll_votes').select('id').eq('poll_id', poll['id']).eq('user_id', user_id).execute()
                    poll['user_voted'] = True if check.data else False
                except Exception:
                    poll['user_voted'] = False
        else:
            for poll in active:
                poll['user_voted'] = False

        # return first 3 by default
        return jsonify({'polls': active[:3]})
    except Exception as e:
        print('api_active_polls error:', e)
        return jsonify({'error': str(e)}), 500


# documenets ---------------------- documents ----------------------

def generate_control_no(prefix='SKLB'):
    now = datetime.now()
    seq = random.randint(100, 999)
    return f"{prefix}-{now.year}{now.month:02d}{now.day:02d}-{seq}"

def generate_pdf_and_get_url(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(13, 42, 82)  # SK Blue

    # Header
    pdf.image("static/images/SKLOGO.png", x=10, y=10, w=20)
    pdf.set_xy(35, 10)
    pdf.cell(0, 10, "Republic of the Philippines", ln=1)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 8, f"Province of {data.get('province','')}", ln=1)
    pdf.cell(0, 8, f"Municipality of {data.get('municipality','')}", ln=1)
    pdf.cell(0, 8, f"Barangay {data.get('barangay','')}", ln=1)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 18)
    pdf.cell(0, 12, "Sangguniang Kabataan", ln=1, align='C')
    pdf.ln(8)

    # Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, data.get('template','').replace('_',' ').title(), ln=1, align='C')
    pdf.ln(5)

    # Body (example for indigency)
    pdf.set_font("Arial", '', 12)
    if data.get('template') == 'indigency':
        pdf.multi_cell(0, 8, f"This is to formally certify that {data.get('name','')}, age {data.get('age','')}, residing at {data.get('address','')}, Barangay {data.get('barangay','')}, {data.get('municipality','')}, {data.get('province','')}, is recognized as a youth of indigent status based on community social assessment and records of the Sangguniang Kabataan.\n\nThis certificate is issued upon the request of the interested party for {data.get('purpose','')}.")
        if data.get('guardian'):
            pdf.multi_cell(0, 8, f"Parent/Guardian: {data.get('guardian')}.")
    # Add other templates similarly...

    pdf.ln(10)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, f"Control No.: {generate_control_no()} | Date Issued: {data.get('date', '')}", ln=1)
    pdf.ln(15)

    # Signatures
    pdf.set_font("Arial", '', 12)
    pdf.cell(80, 8, data.get('sk_chair',''), border='T', align='C')
    pdf.cell(30)
    pdf.cell(80, 8, data.get('sk_sec',''), border='T', align='C')
    pdf.ln(6)
    pdf.cell(80, 8, "SK Chairperson", align='C')
    pdf.cell(30)
    pdf.cell(80, 8, "SK Secretary", align='C')

    # Watermark
    pdf.set_text_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 40)
    pdf.set_xy(60, 230)
    pdf.cell(0, 20, "SK Connect", align='C')

    # Save PDF
    filename = f"static/generated_pdfs/{data.get('template','')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    pdf.output(filename)
    return '/' + filename


@app.route('/api/citizen_documents', methods=['POST'])
def issue_citizen_document():
    data = request.json or {}  # Handle case where request.json is None
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    pdf_url = generate_pdf_and_get_url(data)
    allowed_fields = [
        "code", "title", "category", "status", "date_issued", "project", "tags", "file_url", "doc_type",
        "name", "age", "address", "purpose", "guardian", "years", "recipient", "event", "role", "event_date",
        "scholar", "minor", "relation", "activity", "barangay", "municipality", "province", "sk_chair", "sk_sec",
        "meta", "created_at", "uploaded_by", "pdf_url", "template"
    ]
    insert_data = {k: data.get(k) for k in allowed_fields if k in data}
    insert_data['pdf_url'] = pdf_url
    insert_data['created_at'] = datetime.now(timezone.utc).isoformat()
    # Ensure doc_type is always the same as template
    insert_data['doc_type'] = data.get('template')
    try:
        response = supabase.table("citizen_documents").insert(insert_data).execute()
        saved_doc = response.data[0] if response.data else None
        return jsonify({'success': True, 'pdf_url': pdf_url, 'document': saved_doc})
    except Exception as e:
        print("Supabase insert error:", e)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download_document/<int:doc_id>', methods=['GET'])
def api_download_document(doc_id):
    res = supabase.table("citizen_documents").select("pdf_url").eq("id", doc_id).execute()
    if not res.data:
        return jsonify({'error': 'Document not found'}), 404
    file_url = res.data[0]['pdf_url']
    file_path = file_url.lstrip('/')
    return send_file(file_path, as_attachment=True)

#----------------Volunteer Opportunity API-----------------

# Route: Create new volunteer opportunity (Admin only)
@app.route('/api/volunteer_opportunity', methods=['POST'])
def create_volunteer_opportunity():
    """Create a new volunteer opportunity (SK officials only)"""
    try:
        # Debug session data
        print(f"Session data: {dict(session)}")
        
        # Check if user is logged in
        if 'user_id' not in session:
            print("No user_id in session")
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
            
        user = get_current_user()
        print(f"User data: {user}")
        
        if not user:
            print("No user returned from get_current_user()")
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        # Check if user has permission to create opportunities
        user_position = get_user_attribute(user, 'position', '').lower()
        allowed_positions = ['chairperson', 'secretary', 'treasurer', 'councilor', 'committee head']
        
        print(f"User position: {user_position}")
        print(f"Allowed positions: {allowed_positions}")
        
        if user_position not in allowed_positions:
            return jsonify({'success': False, 'error': 'Only SK officials can create volunteer opportunities'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['title', 'category', 'barangay', 'date', 'start_time', 'end_time', 'description']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({'success': False, 'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        # Handle contact persons - convert array to comma-separated string for database
        contact_persons = data.get('contact_persons', [])
        if not contact_persons or not any(cp.strip() for cp in contact_persons):
            return jsonify({'success': False, 'error': 'At least one contact person is required'}), 400
        
        contact_person_str = ', '.join([cp.strip() for cp in contact_persons if cp.strip()])
        
        # Prepare opportunity data
        opportunity_data = {
            'title': data['title'].strip(),
            'category': data['category'],
            'barangay': data['barangay'],
            'date': data['date'],
            'start_time': data['start_time'],
            'end_time': data['end_time'],
            'description': data['description'].strip(),
            'contact_persons': contact_person_str,  # Changed from contact_person to contact_persons
            'meeting_place': data.get('meeting_place', '').strip() or None,
            'slots': int(data.get('slots', 25)),
            'tshirt_provided': data.get('tshirt_provided', False),  # NEW: T-shirt provision
            'created_by_name': get_user_attribute(user, 'full_name', 'Unknown'),
            'created_by_position': get_user_attribute(user, 'position', 'Unknown'),
            'created_by_id': get_user_attribute(user, 'id'),  # Changed from user_id to id
            'status': 'Active',
            'created_at': datetime.now(timezone.utc).isoformat()  # Add created_at timestamp
        }
        
        # Insert into database
        result = supabase.table('volunteer_opportunities').insert(opportunity_data).execute()
        
        if result.data:
            return jsonify({'success': True, 'message': 'Volunteer opportunity created successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to create opportunity'}), 500
            
    except ValueError as e:
        return jsonify({'success': False, 'error': f'Invalid data: {str(e)}'}), 400
    except Exception as e:
        print(f"Error creating volunteer opportunity: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while creating the opportunity'}), 500

# Route: Get all active volunteer opportunities (For both admin and user pages)
@app.route('/api/volunteer_opportunities', methods=['GET'])
def get_volunteer_opportunities():
    """Get all active volunteer opportunities"""
    try:
        # Fetch all active opportunities
        response = supabase.table('volunteer_opportunities').select('*').eq('status', 'Active').order('created_at', desc=True).execute()
        opportunities = response.data or []
        
        # Format the data for frontend display
        for opp in opportunities:
            # Format dates
            if opp.get('created_at'):
                try:
                    dt = datetime.fromisoformat(opp['created_at'].replace('Z', '+00:00'))
                    opp['created_at_display'] = dt.strftime('%b %d, %Y')
                except:
                    opp['created_at_display'] = 'Unknown'
            
            if opp.get('date'):
                try:
                    dt = datetime.fromisoformat(opp['date'])
                    opp['date_display'] = dt.strftime('%b %d, %Y')
                    opp['day_of_week'] = dt.strftime('%A')
                except:
                    opp['date_display'] = opp['date']
                    
            # Format times
            if opp.get('start_time'):
                try:
                    dt = datetime.strptime(opp['start_time'], '%H:%M')
                    opp['start_time_display'] = dt.strftime('%I:%M %p')
                except:
                    opp['start_time_display'] = opp['start_time']
                    
            if opp.get('end_time'):
                try:
                    dt = datetime.strptime(opp['end_time'], '%H:%M')
                    opp['end_time_display'] = dt.strftime('%I:%M %p')
                except:
                    opp['end_time_display'] = opp['end_time']
            
            # Format creator info
            creator_name = opp.get('created_by_name', 'Unknown')
            creator_position = opp.get('created_by_position', 'Member')
            opp['created_by_display'] = f"{creator_name} ({creator_position})"
        
        return jsonify(opportunities)
        
    except Exception as e:
        print(f"Error fetching volunteer opportunities: {e}")
        return jsonify([]), 500

@app.route('/api/volunteer_opportunity/<int:opportunity_id>', methods=['GET'])
def get_volunteer_opportunity_details(opportunity_id):
    """Get details of a specific volunteer opportunity"""
    try:
        # Fetch the specific opportunity
        response = supabase.table('volunteer_opportunities').select('*').eq('id', opportunity_id).execute()
        
        if not response.data:
            return jsonify({'success': False, 'error': 'Opportunity not found'}), 404
            
        opportunity = response.data[0]
        
        # Format the data for frontend display (same as in the list endpoint)
        if opportunity.get('created_at'):
            try:
                dt = datetime.fromisoformat(opportunity['created_at'].replace('Z', '+00:00'))
                opportunity['created_at_display'] = dt.strftime('%b %d, %Y')
            except:
                opportunity['created_at_display'] = 'Unknown'
        
        if opportunity.get('date'):
            try:
                dt = datetime.fromisoformat(opportunity['date'])
                opportunity['date_display'] = dt.strftime('%b %d, %Y')
                opportunity['day_of_week'] = dt.strftime('%A')
            except:
                opportunity['date_display'] = opportunity['date']
                
        # Format times
        if opportunity.get('start_time'):
            try:
                dt = datetime.strptime(opportunity['start_time'], '%H:%M')
                opportunity['start_time_display'] = dt.strftime('%I:%M %p')
            except:
                opportunity['start_time_display'] = opportunity['start_time']
                
        if opportunity.get('end_time'):
            try:
                dt = datetime.strptime(opportunity['end_time'], '%H:%M')
                opportunity['end_time_display'] = dt.strftime('%I:%M %p')
            except:
                opportunity['end_time_display'] = opportunity['end_time']
        
        # Format creator info
        creator_name = opportunity.get('created_by_name', 'Unknown')
        creator_position = opportunity.get('created_by_position', 'Member')
        opportunity['created_by_display'] = f"{creator_name} ({creator_position})"
        
        # Fetch volunteer signups for this opportunity
        try:
            signup_response = supabase.table('volunteer_signups').select('*').eq('opportunity_id', opportunity_id).order('created_at', desc=True).execute()
            volunteers = signup_response.data or []
            
            # Format volunteer data
            for volunteer in volunteers:
                if volunteer.get('created_at'):
                    try:
                        dt = datetime.fromisoformat(volunteer['created_at'].replace('Z', '+00:00'))
                        volunteer['created_at_display'] = dt.strftime('%b %d, %Y %I:%M %p')
                    except:
                        volunteer['created_at_display'] = 'Unknown'
        except:
            volunteers = []
        
        return jsonify({
            'success': True, 
            'opportunity': opportunity,
            'volunteers': volunteers
        })
        
    except Exception as e:
        print(f"Error fetching opportunity details: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while fetching opportunity details'}), 500

# Route: Get volunteer signups with optional filtering by status or opportunity_id
@app.route('/api/volunteer_signups', methods=['GET'])
def get_volunteer_signups():
    """Get all volunteer signups, optionally filtered by status or opportunity_id"""
    try:
        query = supabase.table('volunteer_signups').select('*, volunteer_opportunities!inner(title, category)')
        
        # Filter by status if provided
        status = request.args.get('status')
        if status:
            # Convert status to proper case
            status = status.capitalize()
            query = query.eq('status', status)
            
        # Filter by opportunity if provided
        opportunity_id = request.args.get('opportunity_id')
        if opportunity_id:
            query = query.eq('opportunity_id', opportunity_id)
            
        response = query.order('created_at', desc=True).execute()
        signups = response.data or []
        
        # Format dates for display and flatten opportunity data
        for signup in signups:
            if signup.get('created_at'):
                try:
                    dt = datetime.fromisoformat(signup['created_at'].replace('Z', '+00:00'))
                    signup['created_at_display'] = dt.strftime('%b %d, %Y %I:%M %p')
                except:
                    signup['created_at_display'] = 'Unknown'
            
            # Add opportunity title and category for easier access
            if signup.get('volunteer_opportunities'):
                signup['opportunity_title'] = signup['volunteer_opportunities']['title']
                signup['category'] = signup['volunteer_opportunities']['category']
        
        return jsonify(signups)
        
    except Exception as e:
        print(f"Error fetching volunteer signups: {e}")
        return jsonify([]), 500

# Route: Create new volunteer signup/application 
@app.route('/api/volunteer_signup', methods=['POST'])
def create_volunteer_signup():
    """Create a new volunteer signup"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['opportunity_id', 'full_name', 'contact', 'email']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({'success': False, 'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        # Check if opportunity provides t-shirt to determine if t-shirt size is required
        opportunity_id = int(data['opportunity_id'])
        opp_response = supabase.table('volunteer_opportunities').select('tshirt_provided').eq('id', opportunity_id).execute()
        
        tshirt_provided = False
        if opp_response.data:
            tshirt_provided = opp_response.data[0].get('tshirt_provided', False)
        
        # If t-shirt is provided, t-shirt size becomes required
        if tshirt_provided and not data.get('tshirt_size'):
            return jsonify({'success': False, 'error': 'T-shirt size is required for this opportunity'}), 400
        
        # Prepare signup data
        signup_data = {
            'opportunity_id': opportunity_id,
            'full_name': data['full_name'].strip(),
            'age': data.get('age'),
            'barangay': data.get('barangay'),
            'contact': data['contact'].strip(),
            'email': data['email'].strip(),
            'facebook': data.get('facebook', '').strip() or None,
            'preferred_role': data.get('preferred_role'),
            'tshirt_size': data.get('tshirt_size') if tshirt_provided else None,  # Only set if t-shirt provided
            'skills': data.get('skills', '').strip() or None,
            'emergency_name': data.get('emergency_name', '').strip() or None,
            'emergency_contact': data.get('emergency_contact', '').strip() or None,
            'status': 'Pending',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Insert into database
        result = supabase.table('volunteer_signups').insert(signup_data).execute()
        
        if result.data:
            return jsonify({'success': True, 'message': 'Volunteer signup submitted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to submit signup'}), 500
            
    except ValueError as e:
        return jsonify({'success': False, 'error': f'Invalid data: {str(e)}'}), 400
    except Exception as e:
        print(f"Error creating volunteer signup: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while submitting signup'}), 500

@app.route('/api/volunteer_signup/<int:signup_id>/status', methods=['PATCH'])
def update_volunteer_signup_status(signup_id):
    """Update the status of a volunteer signup (approve/reject)"""
    try:
        # Check if user is logged in and has permission
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
            
        user = get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        # Check if user has permission to manage signups
        user_position = get_user_attribute(user, 'position', '').lower()
        allowed_positions = ['chairperson', 'secretary', 'treasurer', 'councilor', 'committee head']
        
        if user_position not in allowed_positions:
            return jsonify({'success': False, 'error': 'Only SK officials can manage volunteer signups'}), 403
        
        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({'success': False, 'error': 'Status is required'}), 400
        
        new_status = data['status']
        # Convert frontend status to backend format
        if new_status == 'approve':
            new_status = 'Approved'
        elif new_status == 'reject':
            new_status = 'Rejected'
        
        if new_status not in ['Approved', 'Rejected']:
            return jsonify({'success': False, 'error': 'Status must be either Approved or Rejected'}), 400
        
        # Update the signup status (only update fields that exist in the table)
        result = supabase.table('volunteer_signups').update({
            'status': new_status
        }).eq('id', signup_id).execute()
        
        if result.data:
            return jsonify({'success': True, 'message': f'Volunteer signup {new_status.lower()} successfully'})
        else:
            return jsonify({'success': False, 'error': 'Signup not found'}), 404
            
    except Exception as e:
        print(f"Error updating volunteer signup status: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while updating signup status'}), 500

# --------------------------------- -------  user approval #


@app.route('/approve_user/<user_id>', methods=['POST'])
def approve_user(user_id):
    # Get the current approver's position
    approver_position = session.get('position', '').lower()

    res = supabase.table("sk_users_pending").select("*").eq("id", user_id).execute()
    if not res.data:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    user = res.data[0]
    # include individual name fields that exist in the DB schema: name, Mname, Lname
    allowed_fields = ['username', 'full_name', 'email', 'password', 'position', 'barangay', 'gender', 'birthday', 'name', 'Mname', 'Lname']
    user_data = {k: user[k] for k in allowed_fields if k in user}

    # --- Logic enforcement ---
    position_to_approve = user.get('position', '').lower()

    # Only sadmin can approve chairperson accounts
    if position_to_approve == 'chairperson' and approver_position != 'sadmin':
        flash('Only sadmin can approve chairperson accounts.', 'danger')
        return redirect(url_for('admin_user_approval'))

    # You can add more rules for other positions here if needed

    supabase.table("sk_users").insert(user_data).execute()
    supabase.table("sk_users_pending").delete().eq("id", user_id).execute()
    return redirect(url_for('admin_user_approval'))

@app.route('/reject_user/<user_id>', methods=['POST'])
def reject_user(user_id):
    supabase.table("sk_users_pending").delete().eq("id", user_id).execute()
    return redirect(url_for('admin_user_approval'))

@app.route('/admin_user_approval')
def admin_user_approval():
    approver_position = session.get('position', '').lower()
    response = supabase.table("sk_users_pending").select("*").eq("status", "otp_verified").execute()
    pending_users = response.data if response.data else []

    if approver_position == 'sadmin':
        # Show only pending users with chairperson position
        pending_users = [u for u in pending_users if u.get('position', '').lower() == 'chairperson']
    elif approver_position == 'chairperson':
        # Hide pending users with chairperson position
        pending_users = [u for u in pending_users if u.get('position', '').lower() != 'chairperson']

    return render_template("sk_connect_user_approval.html", pending_users=pending_users)







# ------------------------------ User Profile and Dashboard ------------------------------ #

@app.route('/update_profile', methods=['POST'])
def update_profile():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for('auth'))

    old_password = request.form.get('old_password')
    new_password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    update_data = {}

    # Only allow password change if any password field is filled
    if old_password or new_password or confirm_password:
        # All fields must be filled
        if not (old_password and new_password and confirm_password):
            flash("All password fields are required.", "error")
            return redirect(url_for('profile'))

        # Fetch current password from DB
        user_res = supabase.table("sk_users").select("password").eq("id", user_id).execute()
        if not user_res.data or user_res.data[0]['password'] != old_password:
            flash("Old password is incorrect.", "error")
            return redirect(url_for('profile'))

        if new_password != confirm_password:
            flash("New password and confirm password do not match.", "error")
            return redirect(url_for('profile'))

        update_data["password"] = new_password

    # Only allow profile_pic update if you want
    profile_pic = request.files.get('profile_pic')
    if profile_pic and profile_pic.filename:
        filename = secure_filename(profile_pic.filename or 'profile_pic')
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        profile_pic.save(filepath)
        update_data["profile_pic"] = f"/static/uploads/reports/{filename}"

    if update_data:
        supabase.table("sk_users").update(update_data).eq("id", user_id).execute()
        flash("Profile updated!", "success")
    else:
        flash("Nothing to update.", "info")
    return redirect(url_for('profile'))


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))
    response = supabase.table("sk_users").select("*").eq("id", session['user_id']).execute()
    user = response.data[0] if response.data else None
    # Parse birthday to date object if present and not None
    if user and user.get('birthday'):
        try:
            user['birthday'] = datetime.strptime(user['birthday'], "%Y-%m-%d").date()
        except Exception:
            user['birthday'] = None
    return render_template('sk_connect_profile.html', user=user, now=datetime.utcnow)

@app.route('/check_old_password', methods=['POST'])
def check_old_password():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'valid': False})
    data = request.get_json()
    old_password = data.get('old_password')
    user_res = supabase.table("sk_users").select("password").eq("id", user_id).execute()
    if user_res.data and user_res.data[0]['password'] == old_password:
        return jsonify({'valid': True})
    return jsonify({'valid': False})

# ------------------------------ END User Profile and Dashboard ------------------------------ #

@app.route('/api/profile/qr-data')
def api_profile_qr_data():
    """Return user data for frontend QR generation."""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        res = supabase.table('sk_users').select('*').eq('id', session['user_id']).execute()
        if not res.data:
            return jsonify({'error': 'User not found'}), 404
        
        user = res.data[0]
        
        user_data = {
            'id': user.get('id'),
            'username': user.get('username'),
            'full_name': user.get('full_name'),
            'email': user.get('email'),
            'phone': user.get('phone') or user.get('contact') or user.get('mobile'),
            'position': user.get('position'),
            'barangay': user.get('barangay'),
            'gender': user.get('gender'),
            'birthday': user.get('birthday')
        }
        
        return jsonify({'success': True, 'user': user_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# --- USER TEMPLATES --------------- #


@app.route('/api/attendance/mark', methods=['POST'])
def api_attendance_mark():
    """Mark attendance from QR scan (profile data or manual entry).
    
    Accepts JSON body with:
      - event_id: event ID to mark attendance for
      - user_id: (optional) user ID
      - name: participant name
      - email: participant email
      - phone: (optional) phone number
      - barangay: (optional) barangay
      - status: (optional) attendance status, defaults to 'Present'
    """
    try:
        data = request.get_json(force=True) or {}
        print(f"[Attendance API] Received data: {data}")
    except Exception as e:
        print(f"[Attendance API] JSON parse error: {e}")
        return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400

    now = datetime.utcnow().isoformat()
    try:
        event_id = data.get('event_id')
        if not event_id:
            print("[Attendance API] ERROR: No event_id provided")
            return jsonify({'success': False, 'error': 'event_id is required'}), 400

        name = (data.get('name') or data.get('full_name') or data.get('username') or '').strip()
        email = data.get('email')
        user_id = data.get('user_id')
        phone = data.get('phone', '')
        barangay = data.get('barangay', '')
        status = data.get('status', 'Present')

        # Check if user already has attendance for this event
        if user_id:
            existing = supabase.table('attendances').select('id').eq('event_id', event_id).eq('user_id', user_id).execute()
            if existing.data and len(existing.data) > 0:
                print(f"[Attendance API] ✗ Duplicate: User {user_id} already marked for event {event_id}")
                return jsonify({
                    'success': False, 
                    'error': f'{name} has already been marked present for this event',
                    'duplicate': True
                }), 409

        # Try to find registration_id if user_id is available
        registration_id = None
        if user_id:
            try:
                reg_res = supabase.table('event_registrations').select('id').eq('event_id', event_id).eq('user_id', user_id).execute()
                if reg_res.data and len(reg_res.data) > 0:
                    registration_id = reg_res.data[0]['id']
                    print(f"[Attendance API] Found registration_id {registration_id} for user {user_id}")
            except Exception as reg_err:
                print(f"[Attendance API] Could not fetch registration_id: {reg_err}")
        
        record = {
            'event_id': event_id,
            'registration_id': registration_id,  # can be None
            'user_id': user_id,
            'name': name,
            'email': email,
            'phone': phone,
            'barangay': barangay,
            'status': status,
            'marked_at': now,
        }

        print(f"[Attendance API] Inserting record: {record}")
        result = supabase.table('attendances').insert(record).execute()
        print(f"[Attendance API] ✓ Insert successful: {result}")
        
        return jsonify({'success': True, 'message': f'Attendance marked for {name}', 'record': record}), 200

    except Exception as e:
        print(f"[Attendance API] ✗ Error: {e}")
        app.logger.error(f"attendance mark error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    """Get user data by ID. Used for manual QR entry in attendance scanner."""
    try:
        print(f"[User API] Fetching user {user_id}")
        res = supabase.table('sk_users').select('*').eq('id', user_id).execute()
        
        if not res.data or len(res.data) == 0:
            print(f"[User API] User {user_id} not found")
            return jsonify({'error': 'User not found'}), 404
        
        user = res.data[0]
        print(f"[User API] ✓ User found: {user.get('full_name')}")
        
        return jsonify({
            'id': user.get('id'),
            'user_id': user.get('id'),
            'username': user.get('username'),
            'name': user.get('name'),
            'full_name': user.get('full_name'),
            'email': user.get('email'),
            'phone': user.get('phone'),
            'barangay': user.get('barangay'),
            'position': user.get('position'),
        }), 200
    
    except Exception as e:
        print(f"[User API] Error: {e}")
        app.logger.error(f"user fetch error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/attendance/<int:event_id>', methods=['GET'])
def api_get_attendance(event_id):
    """Get all attendance records for an event."""
    try:
        print(f"[Attendance Fetch] Getting records for event {event_id}")
        
        # Fetch attendance records for this event
        res = supabase.table('attendances').select('*').eq('event_id', event_id).order('marked_at', desc=True).execute()
        
        attendances = res.data if res.data else []
        print(f"[Attendance Fetch] ✓ Found {len(attendances)} records")
        
        # Calculate stats
        total = len(attendances)
        present = sum(1 for a in attendances if a.get('status') == 'Present')
        absent = sum(1 for a in attendances if a.get('status') == 'Absent')
        pending = total - present - absent
        
        return jsonify({
            'success': True,
            'attendances': attendances,
            'stats': {
                'total': total,
                'present': present,
                'absent': absent,
                'pending': pending
            }
        }), 200
    
    except Exception as e:
        print(f"[Attendance Fetch] Error: {e}")
        app.logger.error(f"attendance fetch error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/attendance/<int:event_id>/export', methods=['GET'])
def api_export_attendance(event_id):
    """Export attendance for an event as CSV attachment."""
    try:
        print(f"[Attendance Export] Exporting CSV for event {event_id}")
        # fetch event name for nicer CSV and filename
        ev_res = supabase.table('events').select('name').eq('id', event_id).execute()
        event_name = None
        try:
            event_name = ev_res.data[0].get('name') if ev_res and getattr(ev_res, 'data', None) else None
        except Exception:
            event_name = None

        res = supabase.table('attendances').select('*').eq('event_id', event_id).order('marked_at', desc=True).execute()
        rows = res.data if res.data else []

        si = StringIO()
        writer = csv.writer(si)
        # header (include event_name)
        writer.writerow(['id', 'event_id', 'event_name', 'user_id', 'name', 'email', 'phone', 'barangay', 'status', 'marked_at', 'created_at'])

        for r in rows:
            writer.writerow([
                r.get('id'),
                r.get('event_id'),
                event_name,
                r.get('user_id'),
                r.get('name'),
                r.get('email'),
                r.get('phone'),
                r.get('barangay'),
                r.get('status'),
                r.get('marked_at'),
                r.get('created_at')
            ])

        output = si.getvalue()
        # sanitize filename using event name when available
        if event_name:
            safe = ''.join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in event_name).strip().replace(' ', '_')
            filename = f"attendance_{safe}_{event_id}.csv"
        else:
            filename = f"attendance_event_{event_id}.csv"
        return Response(output, mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename={filename}'
        })

    except Exception as e:
        print(f"[Attendance Export] Error: {e}")
        app.logger.error(f"attendance export error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# @app.route('/api/attendance/<event_id>', methods=['GET'])
# def api_attendance_get(event_id):
#     """Return attendance records and simple stats for an event.

#     Response format: { success: True, registrations: [...], stats: { total: N } }
#     """
#     try:
#         # Fetch records from attendances table
#         res = supabase.table('attendances').select('*').eq('event_id', event_id).order('marked_at', desc=True).execute()
#         rows = res.data if getattr(res, 'data', None) is not None else []

#         # Compute basic stats
#         total = len(rows)

#         # Optionally enrich rows with user info if user_id present
#         registrations = []
#         for r in rows:
#             registrations.append(r)

#         return jsonify({'success': True, 'registrations': registrations, 'stats': {'total': total}})
#     except Exception as e:
#         app.logger.error(f"attendance fetch error: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500



#@app.route('/user_dashboard')
#def user_dashboard():
    user = get_current_user()
    if not user:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))

    user_id = user.get('id')

    # Gather analytics counts across core tables. Best-effort queries with graceful fallback.
    def table_count(table_name):
        try:
            res = supabase.table(table_name).select("id", count="exact").execute()
            # supabase-py places the count on the response when requested
            if hasattr(res, 'count') and res.count is not None:
                return int(res.count)
            # fallback: if .data exists, use its length
            if getattr(res, 'data', None) is not None:
                return len(res.data)
        except Exception:
            pass
        return 0

    from datetime import date
    today = date.today().isoformat()

    stats = {}
    stats['announcements'] = table_count('announcements')
    stats['events_total'] = table_count('events')
    # upcoming events (date >= today)
    try:
        upcoming_res = supabase.table('events').select('id', count='exact').gte('date', today).execute()
        stats['upcoming_events'] = int(upcoming_res.count) if hasattr(upcoming_res, 'count') and upcoming_res.count is not None else (len(upcoming_res.data) if getattr(upcoming_res, 'data', None) is not None else 0)
    except Exception:
        stats['upcoming_events'] = 0

    # events with explicit status 'upcoming' (if your events table uses a status field)
    try:
        status_up_res = supabase.table('events').select('id', count='exact').ilike('status', '%upcoming%').execute()
        stats['events_status_upcoming'] = int(status_up_res.count) if hasattr(status_up_res, 'count') and status_up_res.count is not None else (len(status_up_res.data) if getattr(status_up_res, 'data', None) is not None else 0)
    except Exception:
        # fallback: try exact match
        try:
            status_up_res = supabase.table('events').select('id', count='exact').eq('status', 'upcoming').execute()
            stats['events_status_upcoming'] = int(status_up_res.count) if hasattr(status_up_res, 'count') and status_up_res.count is not None else (len(status_up_res.data) if getattr(status_up_res, 'data', None) is not None else 0)
        except Exception:
            stats['events_status_upcoming'] = 0

    stats['projects'] = table_count('projects')
    stats['users'] = table_count('sk_users')
    stats['financial_reports'] = table_count('financial_reports')
    stats['volunteer_opportunities'] = table_count('volunteer_opportunities')
    stats['volunteer_signups'] = table_count('volunteer_signups')

    # volunteers with active/approved status (not 'Pending')
    try:
        vol_active_res = supabase.table('volunteer_signups').select('id', count='exact').neq('status', 'Pending').execute()
        stats['volunteers_active'] = int(vol_active_res.count) if hasattr(vol_active_res, 'count') and vol_active_res.count is not None else (len(vol_active_res.data) if getattr(vol_active_res, 'data', None) is not None else 0)
    except Exception:
        stats['volunteers_active'] = 0

    # signups for volunteer opportunities that are upcoming (opportunity.date >= today)
    try:
        opp_res = supabase.table('volunteer_opportunities').select('id').gte('date', today).execute()
        opp_ids = [o.get('id') for o in (opp_res.data or []) if o.get('id') is not None]
        if opp_ids:
            # fetch signups whose opportunity_id is in opp_ids
            signups_res = supabase.table('volunteer_signups').select('id', count='exact').in_('opportunity_id', opp_ids).execute()
            stats['volunteers_upcoming'] = int(signups_res.count) if hasattr(signups_res, 'count') and signups_res.count is not None else (len(signups_res.data) if getattr(signups_res, 'data', None) is not None else 0)
        else:
            stats['volunteers_upcoming'] = 0
    except Exception:
        stats['volunteers_upcoming'] = 0
    stats['suggestions'] = table_count('suggestions')
    stats['polls'] = table_count('polls')
    stats['surveys'] = table_count('surveys')
    # Compute active polls: those without an end_date or with end_date >= today
    try:
        polls_res_all = supabase.table('polls').select('*').execute()
        polls_all = polls_res_all.data if getattr(polls_res_all, 'data', None) is not None else []
        active_count = 0
        for p in polls_all:
            end_date = p.get('end_date')
            if not end_date:
                active_count += 1
                continue
            try:
                # normalize and parse ISO datetime
                ed = datetime.fromisoformat(str(end_date).replace('Z', '+00:00'))
                if ed.date().isoformat() >= today:
                    active_count += 1
            except Exception:
                # if we can't parse it, count as active conservatively
                active_count += 1
        stats['polls_active'] = active_count
    except Exception:
        stats['polls_active'] = stats.get('polls', 0)
    stats['transactions_count'] = table_count('transactions')

    # total transaction amount (best-effort): fetch amounts and sum in Python
    try:
        tx_res = supabase.table('transactions').select('amount').execute()
        if getattr(tx_res, 'data', None):
            total_amount = 0.0
            for r in tx_res.data:
                try:
                    amt = float(r.get('amount') or 0)
                except Exception:
                    amt = 0.0
                total_amount += amt
            stats['transactions_total'] = total_amount
        else:
            stats['transactions_total'] = 0.0
    except Exception:
        stats['transactions_total'] = 0.0

    # Keep backward-compatible variable used elsewhere
    total_announcements = stats.get('announcements', 0)

    # pending user approvals (from sk_users_pending where status is 'pending' or null)
    try:
        pend_res = supabase.table('sk_users_pending').select('id', count='exact').or_("status.eq.pending,status.is.null").execute()
        stats['pending_approvals'] = int(pend_res.count) if hasattr(pend_res, 'count') and pend_res.count is not None else (len(pend_res.data) if getattr(pend_res, 'data', None) is not None else 0)
    except Exception:
        # fallback: try simple count
        try:
            pend_res = supabase.table('sk_users_pending').select('id', count='exact').eq('status', 'pending').execute()
            stats['pending_approvals'] = int(pend_res.count) if hasattr(pend_res, 'count') and pend_res.count is not None else (len(pend_res.data) if getattr(pend_res, 'data', None) is not None else 0)
        except Exception:
            stats['pending_approvals'] = 0

    # Also report total pending rows in sk_users_pending (useful for bookkeeping)
    try:
        total_res = supabase.table('sk_users_pending').select('id', count='exact').execute()
        if getattr(total_res, 'count', None) is not None:
            stats['sk_users_pending_rows'] = int(total_res.count)
        else:
            stats['sk_users_pending_rows'] = len(total_res.data) if getattr(total_res, 'data', None) is not None else 0
    except Exception:
        stats['sk_users_pending_rows'] = stats.get('pending_approvals', 0)

    # --- Additional dashboard counts ---
    try:
        # Events needing attendance upload: consider past or today events with enable_qr=true and zero attendance records
        need_count = 0
        try:
            ev_res = supabase.table('events').select('id,date,enable_qr').lte('date', today).eq('enable_qr', True).execute()
            events_list = ev_res.data if getattr(ev_res, 'data', None) is not None else []
            for ev in events_list:
                ev_id = ev.get('id')
                if not ev_id:
                    continue
                att_res = supabase.table('attendances').select('id', count='exact').eq('event_id', ev_id).execute()
                att_count = int(att_res.count) if hasattr(att_res, 'count') and att_res.count is not None else (len(att_res.data) if getattr(att_res, 'data', None) is not None else 0)
                if att_count == 0:
                    need_count += 1
        except Exception:
            need_count = 0
        stats['events_needing_attendance'] = need_count
    except Exception:
        stats['events_needing_attendance'] = 0

    try:
        # Financial reports due this week: look for a `due_date` column between today and 7 days from now
        week_later = (date.today() + timedelta(days=7)).isoformat()
        try:
            fr_res = supabase.table('financial_reports').select('id', count='exact').gte('due_date', today).lte('due_date', week_later).execute()
            if getattr(fr_res, 'count', None) is not None:
                stats['financial_reports_due'] = int(fr_res.count)
            else:
                stats['financial_reports_due'] = len(fr_res.data) if getattr(fr_res, 'data', None) is not None else 0
        except Exception:
            # If `due_date` doesn't exist or query fails, fallback to zero
            stats['financial_reports_due'] = 0
    except Exception:
        stats['financial_reports_due'] = 0

    try:
        # Feedback to review: count suggestions (or feedback) with pending status
        try:
            fb_res = supabase.table('suggestions').select('id', count='exact').or_("status.eq.pending,status.is.null").execute()
            if getattr(fb_res, 'count', None) is not None:
                stats['feedback_to_review'] = int(fb_res.count)
            else:
                stats['feedback_to_review'] = len(fb_res.data) if getattr(fb_res, 'data', None) is not None else 0
        except Exception:
            # fallback: try 'feedback' table if 'suggestions' doesn't match your schema
            try:
                fb_res2 = supabase.table('feedback').select('id', count='exact').or_("status.eq.pending,status.is.null").execute()
                stats['feedback_to_review'] = int(fb_res2.count) if getattr(fb_res2, 'count', None) is not None else (len(fb_res2.data) if getattr(fb_res2, 'data', None) is not None else 0)
            except Exception:
                stats['feedback_to_review'] = 0
    except Exception:
        stats['feedback_to_review'] = 0

    # Fetch recent announcements (latest 5)
    try:
        ann_res = supabase.table('announcements').select('*').order('created_at', desc=True).limit(5).execute()
        recent_announcements = ann_res.data if getattr(ann_res, 'data', None) is not None else []
    except Exception:
        recent_announcements = []

    # Fetch upcoming events (date >= today) limited to 5, ordered soonest first
    try:
        up_ev_res = supabase.table('events').select('*').gte('date', today).order('date', desc=False).limit(5).execute()
        upcoming_events_list = up_ev_res.data if getattr(up_ev_res, 'data', None) is not None else []
    except Exception:
        upcoming_events_list = []

    # Fetch active polls for dashboard (reuse logic similar to api_active_polls)
    try:
        polls_res = supabase.table('polls').select('*').order('created_at', desc=True).execute()
        polls_all = polls_res.data if getattr(polls_res, 'data', None) is not None else []
        active_polls = []
        now = datetime.utcnow()
        for p in polls_all:
            options = p.get('options') or []
            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except Exception:
                    options = []
            votes = p.get('votes') or {}
            total_votes = p.get('total_votes') or 0
            end_date = p.get('end_date')
            ended = False
            if end_date:
                try:
                    edt = datetime.fromisoformat(str(end_date).replace('Z', '+00:00'))
                    if edt < now:
                        ended = True
                except Exception:
                    pass
            if not ended:
                active_polls.append({
                    'id': p.get('id'),
                    'question': p.get('question'),
                    'options': options,
                    'votes': votes,
                    'total_votes': total_votes,
                    'end_date': end_date
                })
    except Exception:
        active_polls = []

    # User-specific additions
    try:
        reg_res = supabase.table('event_registrations').select('id', count='exact').eq('user_id', user_id).execute()
        stats['my_registered_events'] = int(reg_res.count) if hasattr(reg_res, 'count') and reg_res.count is not None else (len(reg_res.data) if getattr(reg_res, 'data', None) is not None else 0)
    except Exception:
        stats['my_registered_events'] = 0

    try:
        feedback_res = supabase.table('suggestions').select('id', count='exact').eq('user_id', user_id).execute()
        stats['my_feedback_count'] = int(feedback_res.count) if hasattr(feedback_res, 'count') and feedback_res.count is not None else (len(feedback_res.data) if getattr(feedback_res, 'data', None) is not None else 0)
    except Exception:
        stats['my_feedback_count'] = 0

    try:
        poll_votes_res = supabase.table('poll_votes').select('poll_id', count='exact').eq('user_id', user_id).execute()
        stats['my_poll_votes'] = int(poll_votes_res.count) if hasattr(poll_votes_res, 'count') and poll_votes_res.count is not None else (len(poll_votes_res.data) if getattr(poll_votes_res, 'data', None) is not None else 0)
    except Exception:
        stats['my_poll_votes'] = 0

    my_events_joined = stats.get('my_registered_events', 0)
    my_volunteer_hours = 0  # Placeholder until hours_logged is implemented

    return render_template(
        'sk_connect_user_dashboard.html',
        stats=stats,
        total_announcements=total_announcements,
        recent_announcements=recent_announcements,
        upcoming_events_list=upcoming_events_list,
        active_polls=active_polls,
        my_events_joined=my_events_joined,
        my_volunteer_hours=my_volunteer_hours,
        full_name=(user or {}).get('full_name', 'User'),
        user=user,
        current_user=user
    )

@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))
    user = get_current_user()
    # If admin roles accidentally hit user dashboard, redirect them to admin area
    pos = (user or {}).get('position', '') or ''
    if pos.lower() in ['chairperson', 'sadmin']:
        return redirect(url_for('admin_dashboard'))
    count_response = supabase.table("announcements").select("id", count="exact").execute()  # type: ignore
    total_announcements = count_response.count if hasattr(count_response, 'count') and count_response.count else 0
    return render_template('sk_connect_user_dashboard.html', total_announcements=total_announcements, full_name=get_user_attribute(user, 'full_name'))

@app.route('/user_announcements')
def user_announcements():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))
    user = get_current_user()

    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 6
    start = (page - 1) * per_page

    # Sorting
    sort = request.args.get('sort', 'newest')
    order_by = 'created_at'
    desc = True
    if sort == 'oldest':
        desc = False
    elif sort == 'alphabetical':
        order_by = 'title'
        desc = False

    # Filtering
    filter_type = request.args.get('type', 'all')

    query = supabase.table("announcements").select("*")
    if filter_type != 'all':
        query = query.eq('type', filter_type)
    query = query.order(order_by, desc=desc)
    response = query.range(start, start + per_page - 1).execute()
    announcements = response.data if response.data else []

    # Get total count for KPI
    count_response = supabase.table("announcements").select("id", count="exact").execute()  # type: ignore
    total_announcements = count_response.count if hasattr(count_response, 'count') and count_response.count else len(announcements)
    # Get total count for pagination (with filter)
    count_query = supabase.table("announcements").select("id", count="exact")  # type: ignore
    if filter_type != 'all':
        count_query = count_query.eq('type', filter_type)
    count_response = count_query.execute()  # type: ignore
    total = count_response.count if hasattr(count_response, 'count') and count_response.count else len(announcements)
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        'sk_connect_user_announcement.html',
        full_name=get_user_attribute(user, 'full_name'),
        announcements=announcements,
        page=page,
        total_pages=total_pages,
        sort=sort,
        filter_type=filter_type,
        time_ago=time_ago,
        total_announcements=total_announcements
    )



@app.route('/user_events_projects')
def user_events_projects():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('auth'))
    user = get_current_user()
    response = supabase.table("events").select("*").order("date", desc=True).execute()
    events = response.data if response.data else []
    now = datetime.now().date()
    return render_template(
        'sk_connect_user_events_projects.html',
        events=events,
        full_name=get_user_attribute(user, 'full_name'),
        today=now
    )


@app.route('/user_financial_report')
def user_financial_report():
    response = supabase.table("projects").select("*").order("created_at", desc=True).limit(3).execute()
    recent_projects = response.data if response.data else []
    tx_response = supabase.table("transactions").select("*").order("date", desc=True).limit(3).execute()
    recent_transactions = tx_response.data if tx_response.data else []
    all_tx_response = supabase.table("transactions").select("*").order("date", desc=True).execute()
    all_transactions = all_tx_response.data if all_tx_response.data else []
    now = datetime.utcnow()
    # Also provide all projects to the user view so client-side charts can use project-derived series
    try:
        all_projects_resp = supabase.table("projects").select("id, budget_allocated, amount_spent, name, category, barangay, status, start_date, end_date").execute()
        all_projects = all_projects_resp.data if all_projects_resp.data else []
        for project in all_projects:
            # normalize numeric fields to simple floats where possible
            try:
                project['budget_allocated'] = float(project.get('budget_allocated') or 0)
            except Exception:
                project['budget_allocated'] = 0
            try:
                project['amount_spent'] = float(project.get('amount_spent') or 0)
            except Exception:
                project['amount_spent'] = 0
    except Exception:
        all_projects = []
    return render_template(
        'sk_connect_user_financial_report.html',
        recent_projects=recent_projects,
        recent_transactions=recent_transactions,
        all_transactions=all_transactions,
        now=now,
        all_projects=all_projects,
        current_user=get_current_user(),
    )

@app.route('/user_feedback')
def user_feedback():
    page = int(request.args.get('page', 1))
    polls_res = supabase.table("polls").select("*").order("created_at", desc=True).execute()
    polls = polls_res.data if polls_res.data else []
    surveys_res = supabase.table("surveys").select("*").order("created_at", desc=True).execute()
    surveys = surveys_res.data if surveys_res.data else []

    # --- Add this block to fetch suggestions ---
    suggestions_res = supabase.table("suggestions").select("*").order("created_at", desc=True).execute()
    suggestions = suggestions_res.data if suggestions_res.data else []
    # Add time_ago for each suggestion
    for s in suggestions:
        s['time_ago'] = time_ago(s['created_at'])
        s['comments'] = []  # If you want to support comments later

    # Format poll end dates
    for poll in polls:
        # Parse options JSON string to Python list
        if isinstance(poll.get('options'), str):
            poll['options'] = json.loads(poll['options'])
        poll['votes'] = poll.get('votes', {}) or {}
        poll['total_votes'] = poll.get('total_votes', 0) or 0
        # Format end_date for display
        if poll.get('end_date'):
            try:
                dt = datetime.fromisoformat(poll['end_date'])
                poll['end_date_display'] = dt.strftime('%Y-%m-%d')
            except Exception:
                poll['end_date_display'] = poll['end_date']
        else:
            poll['end_date_display'] = "Ongoing"

    polls_per_page = 2
    surveys_per_page = 2
    poll_start = (page - 1) * polls_per_page
    poll_end = poll_start + polls_per_page
    survey_start = (page - 1) * surveys_per_page
    survey_end = survey_start + surveys_per_page
    total_pages = max(
        (len(polls) + polls_per_page - 1) // polls_per_page,
        (len(surveys) + surveys_per_page - 1) // surveys_per_page
    )
    return render_template(
        "sk_connect_user_feedback.html",
        polls=polls[poll_start:poll_end],
        surveys=surveys[survey_start:survey_end],
        suggestions=suggestions,
        page=page,
        total_pages=total_pages
    )

@app.route('/user_volunteer')
def user_volunteer():
    if 'user_id' not in session:
        return redirect(url_for('auth'))
    user = get_current_user()
    
    try:
        # Fetch active volunteer opportunities from Supabase
        response = supabase.table('volunteer_opportunities').select('*').eq('status', 'active').order('created_at', desc=True).execute()
        opportunities = response.data or []
        
        # Format dates for display and filter out past opportunities
        current_date = datetime.now().date()
        active_opportunities = []
        
        for opp in opportunities:
            if opp.get('date'):
                opp_date = datetime.fromisoformat(opp['date']).date()
                if opp_date >= current_date:  # Only show current and future opportunities
                    opp['date_display'] = opp_date.strftime('%b %d, %Y')
                    opp['day_of_week'] = opp_date.strftime('%A')
                    
                    # Format times
                    if opp.get('start_time'):
                        opp['start_time_display'] = datetime.strptime(opp['start_time'], '%H:%M').strftime('%I:%M %p')
                    if opp.get('end_time'):
                        opp['end_time_display'] = datetime.strptime(opp['end_time'], '%H:%M').strftime('%I:%M %p')
                    
                    active_opportunities.append(opp)
                    
    except Exception as e:
        active_opportunities = []
        flash(f'Error loading opportunities: {str(e)}', 'error')
    
    return render_template('sk_connect_user_volunteer.html', 
                         full_name=(user or {}).get('full_name'),
                         opportunities=active_opportunities)

@app.route('/user_documents')
def user_documents():
    if 'user_id' not in session:
        return redirect(url_for('auth'))
    user = get_current_user()
    # Fetch all documents from Supabase
    tables = [
        ('barangay_indigency', 'Barangay Indigency (Youth)'),
        ('certificate_residency', 'Certificate of Residency'),
        ('good_moral_character', 'Good Moral Character'),
        ('certificate_participation', 'Certificate of Participation'),
        ('scholarship_endorsement', 'Scholarship Endorsement'),
        ('parental_consent', 'Parental Consent (Minor)'),
        ('citizen_documents', 'Citizen Documents')  # Add this if you want to show PDFs
    ]
    all_docs = []
    for table, doc_type in tables:
        res = supabase.table(table).select('*').execute()
        docs = res.data if res.data else []
        for doc in docs:
            doc['doc_type'] = doc_type
            doc['table'] = table
        all_docs.extend(docs)
    # Sort by created_at descending
    all_docs.sort(key=lambda d: d.get('created_at', ''), reverse=True)
    return render_template('sk_connect_user_document.html', full_name=get_user_attribute(user, 'full_name'), documents=all_docs)



@app.route('/user_training_resources')
def user_training_resources():
    if 'user_id' not in session:
        return redirect(url_for('auth'))

    user = get_current_user()

    try:
        resp = (
            supabase
            .table('training_resources')
            .select('*')
            .order('created_at', desc=True)
            .execute()
        )
        resources = resp.data or []
    except Exception as e:
        print("Error fetching training resources:", e)
        resources = []

    return render_template(
        'sk_connect_user_training.html',
        full_name=get_user_attribute(user, 'full_name'),
        user=user,
        resources=resources
    )

@app.route('/user_incidents')
def user_incidents():
    if 'user_id' not in session:
        return redirect(url_for('auth'))

    user = get_current_user()
    full_name = get_user_attribute(user, 'full_name') if user else ''

    # I-RENDER mo yung user-side HTML (yung view-only wall)
    return render_template('sk_connect_user_incident.html', full_name=full_name)

from flask import jsonify, request

@app.route('/api/youth-warnings-public', methods=['GET'])
def api_youth_warnings_public():
    """
    Read-only list ng youth warnings para sa USER side.
    Same table as admin, pero walang admin check (kailangan lang naka-login).
    Pwede pa rin mag-apply ng filters sa query string.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    # base query – piliin lang yung fields na kailangan ipakita sa user
    query = (
        supabase
        .table('youth_warnings')
        .select(
            'id, youth_name, barangay, violation_type, warning_level, '
            'occurred_at, details, logged_by, action_taken, '
            'consequence_type, service_days_required, service_days_completed'
        )
        .order('occurred_at', desc=True)
    )

    # same filters gaya sa admin GET (optional)
    barangay = request.args.get('barangay')
    vtype    = request.args.get('type')
    level    = request.args.get('level')
    search   = request.args.get('q')
    status   = request.args.get('status')   # optional, kung gagamitin mo sa front-end

    if barangay:
        query = query.eq('barangay', barangay)
    if vtype:
        query = query.eq('violation_type', vtype)
    if level:
        query = query.eq('warning_level', level)

    if search:
        like = f"%{search}%"
        query = query.or_(
            "youth_name.ilike.{0},details.ilike.{0},action_taken.ilike.{0}".format(like)
        )

    # NOTE: kung gusto mo ng field na `is_archived` / `visible_to_public`,
    # pwede kang mag-query dito:
    # query = query.eq('visible_to_public', True)

    resp = query.execute()
    data = resp.data or []

    # optional: kung gusto mong mag-hide ng super sensitive info, pwede mo pang
    # i-process dito bago ibalik sa user.

    return jsonify(data), 200




@app.route('/user_community')
def user_community():
    if 'user_id' not in session:
        return redirect(url_for('auth'))
    user = get_current_user()
    page = int(request.args.get('page', 1))
    suggestions_res = supabase.table("suggestions").select("*").order("created_at", desc=True).execute()
    suggestions = suggestions_res.data if suggestions_res.data else []
    for s in suggestions:
        s['time_ago'] = time_ago(s['created_at'])
        s['comments'] = []
    return render_template(
        "sk_connect_user_community.html",
        suggestions=suggestions,
        page=page,
        full_name=get_user_attribute(user, 'full_name')
    )

@app.route('/api/events')
def api_events():
    """API endpoint to fetch events for calendar display"""
    try:
        response = supabase.table('events').select('*').execute()
        events = response.data if response.data else []
        
        # Format for FullCalendar
        formatted_events = []
        for event in events:
            formatted_events.append({
                'title': event.get('name', 'Event'),
                'start': event.get('date') or event.get('start'),
                'end': event.get('end'),
                'id': event.get('id')
            })
        
        return jsonify(formatted_events)
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify([]), 500



@app.route('/submit_suggestion', methods=['POST'])
def user_submit_suggestion():
    title = request.form.get('title')
    category = request.form.get('category')
    description = request.form.get('description')
    author = request.form.get('author', 'Anonymous')

    data = {
        "title": title,
        "category": category,
        "description": description,
        "author": author,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        supabase.table("suggestions").insert(data).execute()
        flash('Suggestion submitted successfully!', 'success')
    except Exception as e:
        print("Supabase insert error:", e)
        flash('Failed to submit suggestion.', 'danger')

    return redirect(url_for('user_community'))


print("SUPABASE_URL:", url)
print("SUPABASE_KEY:", key[:5] + "..." if key else None)

app.jinja_env.filters['loads'] = json.loads


@app.route('/citizen/<table>/<int:doc_id>', methods=['DELETE'])
def delete_citizen_document(table, doc_id):
    try:
        supabase.table(table).delete().eq('id', doc_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500






#


@app.route('/admin_all_projects')
def admin_all_projects():
    # Get all projects with complete data for the main table
    try:
        all_projects_response = supabase.table("projects").select("*").order("created_at", desc=True).execute()
        all_projects = all_projects_response.data if all_projects_response.data else []
        
        # Calculate progress and parse dates for each project
        for project in all_projects:
            # Calculate progress
            try:
                budget = float(project.get('budget_allocated') or 0)
                spent = float(project.get('amount_spent') or 0)
                project['progress'] = round((spent / budget * 100) if budget > 0 else 0)
            except (ValueError, TypeError):
                project['progress'] = 0
                
            # Parse dates if they exist
            try:
                if project.get('start_date'):
                    project['start_date'] = datetime.strptime(project['start_date'], '%Y-%m-%d').date()
                if project.get('end_date'):
                    project['end_date'] = datetime.strptime(project['end_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                # If date parsing fails, keep as string
                pass
    except Exception:
        all_projects = []
    
    # Get recent projects for other UI elements that need them
    response = supabase.table("projects").select("*").order("created_at", desc=True).limit(3).execute()
    recent_projects = response.data if response.data else []
    tx_response = supabase.table("transactions").select("*").order("date", desc=True).limit(3).execute()
    recent_transactions = tx_response.data if tx_response.data else []
    all_tx_response = supabase.table("transactions").select("*").order("date", desc=True).execute()
    all_transactions = all_tx_response.data if all_tx_response.data else []
    now = datetime.utcnow()

    total_budget = 0.0
    total_spent = 0.0
    for p in all_projects:
        try:
            b = float(p.get('budget_allocated') or 0)
        except Exception:
            b = 0.0
        try:
            s = float(p.get('amount_spent') or 0)
        except Exception:
            s = 0.0
        total_budget += b
        total_spent += s

    remaining = max(total_budget - total_spent, 0.0)
    percent_spent = (total_spent / total_budget * 100.0) if total_budget > 0 else 0.0

    return render_template(
        'sk_connect_all_projects.html',
        all_projects=all_projects,  # All projects for the main table
        recent_projects=recent_projects,  # Recent projects for other UI elements
        recent_transactions=recent_transactions,
        all_transactions=all_transactions,
        total_budget=total_budget,
        total_spent=total_spent,
        remaining=remaining,
        percent_spent=percent_spent,
        now=now,
        current_user=get_current_user()
    )







if __name__ == '__main__':
    # Print the local IP for convenience and bind to 0.0.0.0 so other devices on the LAN can reach the dev server.
    try:
        local_ip = get_local_ip()
    except Exception:
        local_ip = '127.0.0.1'
    print(f"App starting. Open on this machine: http://127.0.0.1:5001")
    print(f"App reachable on your LAN at: http://{local_ip}:5001")
    app.run(host='0.0.0.0', debug=True, port=5001)
