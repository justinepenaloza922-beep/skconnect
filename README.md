# SK Connect

A Flask-based community management app (SK Connect).

## Summary
This repository contains the SK Connect web application — a Flask app that uses Supabase for backend data storage and provides features for announcements, events, documents, polls, surveys, and project/financial management.

## Prerequisites
- Python 3.10+
- pip
- (Optional) Virtualenv or conda
- Supabase project and API keys

## Quick setup
1. Clone the repo (already done):

```bash
git clone https://github.com/justinepenaloza922-beep/skconnect.git
cd "SK_CONNECT_v18 Stable"
```

2. Create virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-celery.txt || true
# If you have a requirements.txt, also run:
# pip install -r requirements.txt
```

3. Create environment variables (example):

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-anon-or-service-key"
export SECRET_KEY="a-secure-flask-secret"
export FLASK_ENV=development
```

4. Ensure upload folders exist:

```bash
mkdir -p static/generated_pdfs static/uploads static/uploads/documents
```

5. Run locally:

```bash
python run_local.py
# or
python app.py
# or
flask run
```

## Notes
- Do NOT commit secrets: `.env` is included in `.gitignore`.
- Uploaded/generated files in `static/generated_pdfs` and `static/uploads` are ignored by git.
- The app references Supabase tables; ensure your Supabase schema matches the SQL files in `sql/`.

## Next steps I can do for you
- Add a more detailed `requirements.txt` and `setup` script
- Add GitHub Actions CI for linting/tests
- Remove large binary files from Git history or use `git-lfs`

If you want one of the above, tell me which and I'll implement it.