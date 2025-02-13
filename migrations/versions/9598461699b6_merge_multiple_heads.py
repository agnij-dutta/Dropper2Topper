"""Merge multiple heads

Revision ID: 9598461699b6
Revises: 74f372186050, add_feedback_to_score
Create Date: 2025-02-13 03:33:42.142866

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9598461699b6'
down_revision = ('74f372186050', 'add_feedback_to_score')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
