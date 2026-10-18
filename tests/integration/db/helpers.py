"""Row builders shared by the database tests."""

from __future__ import annotations

from sqlalchemy.orm import Session

from vidgen.infrastructure.db.models import Campaign, Template


def make_campaign(session: Session) -> Campaign:
    """Insert a campaign."""
    campaign = Campaign(name="Test campaign")
    session.add(campaign)
    session.flush()
    return campaign


def make_template(session: Session, campaign: Campaign) -> Template:
    """Insert a template with probe facts."""
    template = Template(
        campaign_id=campaign.id,
        video_key="templates/t.mp4",
        original_name="Krishan",
        duration_s=4.0,
        width=320,
        height=240,
    )
    session.add(template)
    session.flush()
    return template
