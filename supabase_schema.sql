-- ============================================================
-- Sitare Sports Management Portal - Supabase (PostgreSQL) Schema
-- Run this in Supabase -> SQL Editor -> New Query -> Run
-- ============================================================

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    pw TEXT NOT NULL,
    override INTEGER NOT NULL DEFAULT 0
);

-- 2. Equipment Table
CREATE TABLE IF NOT EXISTS equipment (
    id SERIAL PRIMARY KEY,
    sku TEXT UNIQUE,
    name TEXT NOT NULL,
    sport TEXT NOT NULL,
    brand TEXT DEFAULT '',
    rack TEXT DEFAULT '',
    grade TEXT NOT NULL DEFAULT 'A',
    status TEXT NOT NULL DEFAULT 'available',
    photo TEXT DEFAULT ''
);

-- 3. Loans Table
CREATE TABLE IF NOT EXISTS loans (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id),
    lead_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'requested',
    hours INTEGER NOT NULL DEFAULT 4,
    requested_at TEXT,
    issued_at TEXT,
    due_at TEXT,
    returned_at TEXT,
    issue_grade TEXT,
    issue_notes TEXT DEFAULT '',
    return_grade TEXT,
    return_notes TEXT DEFAULT '',
    fine NUMERIC(10,2) NOT NULL DEFAULT 0,
    issue_photo TEXT DEFAULT '',
    return_photo TEXT DEFAULT ''
);

-- 4. Loan Members Table
CREATE TABLE IF NOT EXISTS loan_members (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    share NUMERIC(10,2) NOT NULL DEFAULT 0,
    paid INTEGER NOT NULL DEFAULT 0
);

-- 5. Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    user_name TEXT,
    action TEXT NOT NULL,
    details TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

-- 6. Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'info',
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Helpful indices for performance
CREATE INDEX IF NOT EXISTS idx_loans_equipment ON loans(equipment_id);
CREATE INDEX IF NOT EXISTS idx_loans_lead ON loans(lead_id);
CREATE INDEX IF NOT EXISTS idx_loan_members_loan ON loan_members(loan_id);
CREATE INDEX IF NOT EXISTS idx_loan_members_user ON loan_members(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
