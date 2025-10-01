"""Sync after manual ON DELETE CASCADE fix

Revision ID: ca1808576c26
Revises: db8078b400af
Create Date: 2025-10-01 18:52:15.358957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ca1808576c26'
down_revision = 'db8078b400af'
branch_labels = None
depends_on = None


def upgrade():
    # -------------------------------------------------------------
    # 1. FacultyAssignment -> DefaultSchedule CASCADE
    # Constraint Name: default_schedule_assignment_id_fkey
    # -------------------------------------------------------------
    FK_SCHEDULE_ASSIGNMENT = 'default_schedule_assignment_id_fkey'
    op.drop_constraint(FK_SCHEDULE_ASSIGNMENT, 'default_schedule', type_='foreignkey')
    op.create_foreign_key(
        FK_SCHEDULE_ASSIGNMENT, 
        'default_schedule', 
        'faculty_assignment',
        ['assignment_id'], 
        ['id'],
        ondelete='CASCADE' 
    )

    # -------------------------------------------------------------
    # 2. Subject -> FacultyAssignment CASCADE
    # Constraint Name: faculty_assignment_subject_code_fkey (Assumed)
    # -------------------------------------------------------------
    FK_ASSIGNMENT_SUBJECT = 'faculty_assignment_subject_code_fkey'
    op.drop_constraint(FK_ASSIGNMENT_SUBJECT, 'faculty_assignment', type_='foreignkey')
    op.create_foreign_key(
        FK_ASSIGNMENT_SUBJECT, 
        'faculty_assignment', 
        'subject',
        ['subject_code'],         
        ['subject_code'],         
        ondelete='CASCADE' 
    )

def downgrade():
    # -------------------------------------------------------------
    # 1. Reverse FacultyAssignment -> DefaultSchedule CASCADE
    # -------------------------------------------------------------
    FK_SCHEDULE_ASSIGNMENT = 'default_schedule_assignment_id_fkey'
    op.drop_constraint(FK_SCHEDULE_ASSIGNMENT, 'default_schedule', type_='foreignkey')
    op.create_foreign_key(
        FK_SCHEDULE_ASSIGNMENT, 
        'default_schedule', 
        'faculty_assignment',
        ['assignment_id'], 
        ['id'],
        ondelete=None
    )

    # -------------------------------------------------------------
    # 2. Reverse Subject -> FacultyAssignment CASCADE
    # -------------------------------------------------------------
    FK_ASSIGNMENT_SUBJECT = 'faculty_assignment_subject_code_fkey'
    op.drop_constraint(FK_ASSIGNMENT_SUBJECT, 'faculty_assignment', type_='foreignkey')
    op.create_foreign_key(
        FK_ASSIGNMENT_SUBJECT, 
        'faculty_assignment', 
        'subject',
        ['subject_code'], 
        ['subject_code'], 
        ondelete=None
    )
