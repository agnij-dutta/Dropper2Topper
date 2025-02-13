"""Add feedback column to Score model

Revision ID: add_feedback_to_score
Revises: e5b717dc85df
Create Date: 2024-02-13 02:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_feedback_to_score'
down_revision = 'e5b717dc85df'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('score', sa.Column('feedback', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('score', 'feedback')