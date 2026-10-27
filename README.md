# Sitare Sports Desk

Flask + SQLite platform for issuing and returning sports gear to groups of 3-4 students.

    pip install -r requirements.txt
    python app.py          # http://127.0.0.1:5000

Coordinator login: `sports@sitare.org` / `coord123`.
Set `ADMIN_PASSWORD`, `SECRET_KEY` and `COORDINATORS` (comma-separated emails) before deploying.
Students sign in with any `@sitare.org` email; the first login creates the account and sets its password.
Delete `sports.db` to reset.
