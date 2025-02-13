"""Add lecture and AI-generated content models

Revision ID: b7acc3b69c2d
Revises: 7ec54dd1e4b9
Create Date: 2025-02-11 23:52:20.314447

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7acc3b69c2d'
down_revision = '7ec54dd1e4b9'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_ai_generated', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('source_lecture_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_quiz_lecture', 'lecture', ['source_lecture_id'], ['id'])

    with op.batch_alter_table('score', schema=None) as batch_op:
        batch_op.alter_column('time_taken',
               existing_type=sa.INTEGER(),
               nullable=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('score', schema=None) as batch_op:
        batch_op.alter_column('time_taken',
               existing_type=sa.INTEGER(),
               nullable=True)

    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.drop_constraint('fk_quiz_lecture', type_='foreignkey')
        batch_op.drop_column('source_lecture_id')
        batch_op.drop_column('is_ai_generated')

    # ### end Alembic commands ###
