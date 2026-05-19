import os
import json
import re
from datetime import datetime, timezone
from celery_worker import celery_app
from supabase import create_client

# Supabase client for tasks
url = os.environ.get('SUPABASE_URL')
key = os.environ.get('SUPABASE_KEY')
if not url or not key:
    raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set for Celery tasks')
supabase = create_client(url, key)

import smtplib
from email.mime.text import MIMEText


def insert_with_schema_fallback(table_name, payload):
    """Resilient insert that strips missing columns reported by Supabase."""
    payload = dict(payload)
    attempts = 0
    while True:
        attempts += 1
        try:
            return supabase.table(table_name).insert(payload).execute()
        except Exception as err:
            msg = str(err)
            m = re.search(r"Could not find the '([^']+)' column", msg)
            if not m:
                raise
            col = m.group(1)
            if col in payload:
                print(f"[SCHEDULED TASK] Removing missing column from payload: {col}")
                payload.pop(col, None)
                if attempts >= 10:
                    raise
                continue
            else:
                raise



@celery_app.task(name='tasks.announcement_tasks.process_scheduled_announcements')
def process_scheduled_announcements():
    """Find scheduled announcements and post them when their schedule time is reached."""
    try:
        now_utc = datetime.now(timezone.utc)
        print(f"[SCHEDULED TASK] Running at {now_utc.isoformat()}")
        resp = supabase.table('scheduled_announcements').select('*').eq('schedule_post', True).eq('processed', False).execute()
        rows = resp.data if getattr(resp, 'data', None) is not None else []
        print(f"[SCHEDULED TASK] Found {len(rows)} unprocessed scheduled announcements")
        for ann in rows:
            sched = ann.get('schedule_time')
            if not sched:
                continue
            try:
                normalized = sched.replace('Z', '+00:00') if isinstance(sched, str) else sched
                sched_dt = datetime.fromisoformat(normalized)
                if sched_dt.tzinfo is None:
                    sched_dt = sched_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                sched_dt = sched_dt.astimezone(timezone.utc)
            except Exception:
                continue

            print(f"[SCHEDULED TASK] Announcement ID={ann.get('id')}: scheduled_time={sched_dt.isoformat()}, now={now_utc.isoformat()}, ready={sched_dt <= now_utc}")
            if sched_dt <= now_utc:
                print(f"[SCHEDULED TASK] Publishing announcement ID={ann.get('id')} - time reached!")
                announcement_data = {
                    'title': ann.get('title'),
                    'description': ann.get('description'),
                    'type': ann.get('type'),
                    'created_at': sched,  # Use scheduled time as the created_at, not current time
                    'send_notification': ann.get('send_notification', False),
                    'views': 0
                }

                try:
                    insert_res = insert_with_schema_fallback("announcements", announcement_data)
                    print(f"[SCHEDULED TASK] Successfully inserted announcement ID={ann.get('id')} into announcements table")
                except Exception as ex:
                    print(f"[SCHEDULED TASK] Failed to publish scheduled announcement ID={ann.get('id')}: {ex}")
                    continue

                sent_count = 0
                print(f"[SCHEDULED TASK] send_notification={ann.get('send_notification')} for announcement ID={ann.get('id')}")
                if ann.get('send_notification'):
                    print(f"[SCHEDULED TASK] Fetching users for email notification of announcement ID={ann.get('id')}")
                    users_resp = supabase.table('sk_users').select('id,email').execute()
                    users = users_resp.data if getattr(users_resp, 'data', None) is not None else []
                    emails = [u.get('email') for u in users if u.get('email')]
                    print(f"[SCHEDULED TASK] Found {len(emails)} users with email addresses")

                    smtp_host = os.environ.get('SMTP_HOST') or 'smtp.gmail.com'
                    smtp_port = int(os.environ.get('SMTP_PORT', 587))
                    smtp_user = os.environ.get('SMTP_USER') or os.environ.get('SMTP_EMAIL')
                    smtp_pass = os.environ.get('SMTP_PASS') or os.environ.get('SMTP_PASSWORD')
                    from_addr = os.environ.get('FROM_EMAIL') or smtp_user
                    print(f"[SCHEDULED TASK] SMTP config: host={smtp_host}, port={smtp_port}, user={smtp_user}, from={from_addr}")
                    if smtp_host and smtp_user and smtp_pass and from_addr and emails:
                        try:
                            failed = []
                            chunk_size = int(os.environ.get('SMTP_CHUNK_SIZE', 50))
                            print(f"Scheduled announcement email: sending to {len(emails)} recipients in chunks of {chunk_size}")
                            for chunk_start in range(0, len(emails), chunk_size):
                                chunk = emails[chunk_start:chunk_start + chunk_size]
                                server = smtplib.SMTP(smtp_host, smtp_port)
                                server.starttls()
                                server.login(smtp_user, smtp_pass)
                                for e in chunk:
                                    try:
                                        msg = MIMEText(ann.get('description') or '', 'plain', 'utf-8')
                                        msg['Subject'] = ann.get('title') or ''
                                        msg['From'] = from_addr
                                        msg['To'] = e
                                        send_result = server.sendmail(from_addr, e, msg.as_string())
                                        if send_result:
                                            failed.append({'email': e, 'error': str(send_result)})
                                            print(f"Email send to {e} failed: {send_result}")
                                        else:
                                            sent_count += 1
                                    except Exception as ex:
                                        failed.append({'email': e, 'error': str(ex)})
                                        print(f"Email send to {e} failed: {ex}")
                                server.quit()
                            print(f"Scheduled announcement send complete: sent={sent_count}, failed={len(failed)}")
                        except Exception as ex:
                            sent_count = 0
                            print(f"SMTP send error: {ex}")
                    else:
                        print(f"Scheduled announcement email skipped: SMTP not configured or no emails found. smtp_host={smtp_host} smtp_user={smtp_user} emails={len(emails)}")

                try:
                    supabase.table('scheduled_announcements').update({'processed': True}).eq('id', ann.get('id')).execute()
                    print(f"[SCHEDULED TASK] Marked announcement ID={ann.get('id')} as processed")
                except Exception as ex:
                    print(f"[SCHEDULED TASK] Failed to mark scheduled announcement ID={ann.get('id')} processed: {ex}")

    except Exception as e:
        print(f"Error in scheduled announcements task: {e}")
