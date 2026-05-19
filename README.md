# SK Connect

Flask-based community management application used for announcements, events, documents, polls, surveys, and financial/project tracking.

## Repository layout
- `app.py` — main Flask application (routes and logic).
- `templates/` — Jinja2 HTML templates used by the app.
- `static/` — static assets (CSS, JS, images, uploads, generated PDFs).
- `sql/` — SQL migration / schema and helper scripts.
- `scripts/` — utility scripts (data import, maintenance).
- `requirements-celery.txt` — dependencies used by the project (worker/production).

## Quick start (development)
1. Clone the repo:

```bash
git clone https://github.com/justinepenaloza922-beep/skconnect.git
cd "SK_CONNECT_v18 Stable"
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements-celery.txt
# If you have an additional requirements.txt, run:
# pip install -r requirements.txt
```

4. Set required environment variables (example):

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-service-or-anon-key"
export SECRET_KEY="a-secure-flask-secret"
export FLASK_ENV=development
```

5. Ensure upload directories exist:

```bash
mkdir -p static/generated_pdfs static/uploads static/uploads/documents
```

6. Run the app locally:

```bash
python run_local.py
# or
flask run
```

## Testing & CI
- A GitHub Actions workflow is included at `.github/workflows/python-ci.yml` to run linting (flake8) and tests (pytest).

## Configuration & secrets
- Do not commit secrets. Use environment variables or a `.env` file that is included in `.gitignore`.
- Verify Supabase credentials and DB schema before running the app; SQL schema files are under `sql/`.

## Common tasks I can help with
- Generate a `requirements.txt` from your environment.
- Remove large generated files from the repo history or configure `git-lfs`.
- Add more detailed setup scripts, Dockerfile, or GitHub Pages/Heroku deployment steps.

If you want me to commit and push any of the above changes, tell me which and I'll implement them.