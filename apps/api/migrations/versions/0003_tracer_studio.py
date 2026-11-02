"""Add R4 Golf Tracer Studio additive tables

Revision ID: 0003_tracer_studio
Revises: 0002_reference_swings
Create Date: 2026-10-31 17:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tracer_studio"
down_revision: str | None = "0002_reference_swings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRACER_TABLES = [
    "tracer_exports",
    "tracer_render_recipes",
    "tracer_anchor_revisions",
    "tracer_manual_edits",
    "tracer_track_revisions",
    "tracer_jobs",
    "tracer_projects",
    "tracer_model_registry",
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    if "tracer_projects" not in existing:
        op.create_table(
            "tracer_projects",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("practice_sessions.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("segment_id", sa.String(36), sa.ForeignKey("swing_segments.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(200), nullable=False, server_default="Golf Tracer Studio Project"),
            sa.Column("status", sa.String(32), nullable=False, server_default="ready", index=True),
            sa.Column("swing_status", sa.String(32), nullable=False, server_default="NEEDS_REVIEW"),
            sa.Column("shot_mode", sa.String(32), nullable=False, server_default="UNAVAILABLE"),
            sa.Column("active_swing_revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("active_shot_revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("active_anchor_revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("active_recipe_id", sa.String(36), nullable=True),
            sa.Column("source_video_sha256", sa.String(64), nullable=False, server_default=""),
            sa.Column("coordinate_space_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "tracer_jobs" not in existing:
        op.create_table(
            "tracer_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("tracer_projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("job_type", sa.String(32), nullable=False, server_default="auto_trace"),
            sa.Column("state", sa.String(32), nullable=False, server_default="queued", index=True),
            sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("stage_message", sa.String(255), nullable=False, server_default=""),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("result_summary_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "tracer_track_revisions" not in existing:
        op.create_table(
            "tracer_track_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("tracer_projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("track_type", sa.String(32), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("parent_revision", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="NEEDS_REVIEW"),
            sa.Column("storage_key", sa.String(512), nullable=True),
            sa.Column("artifact_sha256", sa.String(64), nullable=True),
            sa.Column("point_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("points_inline_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("quality_summary_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_by", sa.String(32), nullable=False, server_default="model"),
            sa.Column("note", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "track_type", "revision", name="uq_tracer_track_proj_type_rev"),
        )
        op.create_index("ix_tracer_track_proj_type", "tracer_track_revisions", ["project_id", "track_type"])

    if "tracer_manual_edits" not in existing:
        op.create_table(
            "tracer_manual_edits",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("tracer_projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("track_type", sa.String(32), nullable=False),
            sa.Column("base_revision", sa.Integer(), nullable=False),
            sa.Column("new_revision", sa.Integer(), nullable=False),
            sa.Column("operations_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("note", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "tracer_anchor_revisions" not in existing:
        op.create_table(
            "tracer_anchor_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("tracer_projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("address_pts_us", sa.BigInteger(), nullable=True),
            sa.Column("top_pts_us", sa.BigInteger(), nullable=True),
            sa.Column("impact_pts_us", sa.BigInteger(), nullable=True),
            sa.Column("finish_pts_us", sa.BigInteger(), nullable=True),
            sa.Column("launch_pts_us", sa.BigInteger(), nullable=True),
            sa.Column("apex_pts_us", sa.BigInteger(), nullable=True),
            sa.Column("landing_pts_us", sa.BigInteger(), nullable=True),
            sa.Column("anchors_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_by", sa.String(32), nullable=False, server_default="system"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "revision", name="uq_tracer_anchor_proj_rev"),
        )

    if "tracer_render_recipes" not in existing:
        op.create_table(
            "tracer_render_recipes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("tracer_projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("preset_id", sa.String(64), nullable=False, server_default="studio_neon"),
            sa.Column("name", sa.String(120), nullable=False, server_default="Studio Neon"),
            sa.Column("recipe_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "tracer_exports" not in existing:
        op.create_table(
            "tracer_exports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("tracer_projects.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("project_ids_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("segment_ids_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("aspect_ratio", sa.String(16), nullable=False, server_default="original"),
            sa.Column("fps", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("audio_mode", sa.String(16), nullable=False, server_default="preserve"),
            sa.Column("state", sa.String(32), nullable=False, server_default="queued", index=True),
            sa.Column("mp4_storage_key", sa.String(512), nullable=True),
            sa.Column("sidecar_storage_key", sa.String(512), nullable=True),
            sa.Column("mp4_sha256", sa.String(64), nullable=True),
            sa.Column("sidecar_sha256", sa.String(64), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("output_width", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("output_height", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("has_audio_stream", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("recipe_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("parity_report_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("sidecar_payload_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "tracer_model_registry" not in existing:
        op.create_table(
            "tracer_model_registry",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("model_role", sa.String(32), nullable=False, index=True),
            sa.Column("display_name", sa.String(120), nullable=False),
            sa.Column("weights_path", sa.String(512), nullable=False, server_default=""),
            sa.Column("weights_sha256", sa.String(64), nullable=True),
            sa.Column("license_spdx", sa.String(64), nullable=False, server_default="MIT"),
            sa.Column("availability_status", sa.String(64), nullable=False, server_default="READY"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())
    for tbl in TRACER_TABLES:
        if tbl in existing:
            op.drop_table(tbl)
