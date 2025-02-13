"""Replace Chapter model with direct Subject-Lecture relationship
Revision ID: e5b717dc85df
Revises: b7acc3b69c2d
Create Date: 2025-02-12 01:04:40.587066
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'e5b717dc85df'
down_revision = 'b7acc3b69c2d'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()

    # Drop columns without explicitly naming the constraints (SQLite will handle them)
    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.drop_column('chapter_id')

    with op.batch_alter_table('lecture', schema=None) as batch_op:
        batch_op.drop_column('chapter_id')

    # Drop the chapter table
    op.drop_table('chapter')

def downgrade():
    # Create chapter table
    op.create_table('chapter',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('subject_id', sa.INTEGER(), nullable=False),
        sa.Column('name', sa.VARCHAR(length=100), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=True),
        sa.ForeignKeyConstraint(['subject_id'], ['subject.id'], name='fk_chapter_subject'),
        sa.PrimaryKeyConstraint('id')
    )

    # Add back old columns
    with op.batch_alter_table('lecture', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chapter_id', sa.INTEGER(), nullable=True))

    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chapter_id', sa.INTEGER(), nullable=True))

    # Create default chapters and migrate data
    conn = op.get_bind()

    # Create default chapters for each subject
    conn.execute(text("""
        INSERT INTO chapter (subject_id, name)
        SELECT DISTINCT subject_id, 'Default Chapter'
        FROM lecture
    """))

    # Update lectures with chapter_id
    conn.execute(text("""
        UPDATE lecture
        SET chapter_id = (
            SELECT id
            FROM chapter
            WHERE chapter.subject_id = lecture.subject_id
            LIMIT 1
        )
    """))

    # Update quizzes with chapter_id based on their lectures
    conn.execute(text("""
        UPDATE quiz
        SET chapter_id = (
            SELECT chapter_id
            FROM lecture
            WHERE lecture.id = quiz.source_lecture_id
        )
    """))

    # Make columns non-nullable and create foreign keys
    with op.batch_alter_table('lecture', schema=None) as batch_op:
        batch_op.alter_column('chapter_id', nullable=False)
        batch_op.create_foreign_key('fk_lecture_chapter', 'chapter', ['chapter_id'], ['id'])

    with op.batch_alter_table('quiz', schema=None) as batch_op:
        batch_op.alter_column('chapter_id', nullable=False)
        batch_op.create_foreign_key('fk_quiz_chapter', 'chapter', ['chapter_id'], ['id'])
