import sqlite3
import subprocess
import sys


def test_seed_cli_is_idempotent_and_preserves_existing_app_state(tmp_path, monkeypatch):
    path = tmp_path / 'demo.sqlite3'
    monkeypatch.setenv('AI_DATABASE_PATH', str(path))
    subprocess.run([sys.executable, '-m', 'app.seed'], check=True, cwd=tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE demo_user_state(value TEXT)')
        db.execute("INSERT INTO demo_user_state VALUES ('保持')")
    subprocess.run([sys.executable, '-m', 'app.seed'], check=True, cwd=tmp_path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM contracts').fetchone() == (10,)
        assert db.execute('SELECT COUNT(*) FROM monthly_sales').fetchone() == (13,)
        assert db.execute("SELECT SUM(revenue_cents) FROM monthly_sales WHERE contract_id IN ('c1','c2')").fetchone() == (3000000000,)
        assert db.execute("SELECT COUNT(*) FROM projects WHERE risk='高风险'").fetchone() == (3,)
        assert db.execute('SELECT DISTINCT version,as_of FROM dataset').fetchall() == [('demo-1', '2026-08-31')]
        assert db.execute('SELECT value FROM demo_user_state').fetchone() == ('保持',)
