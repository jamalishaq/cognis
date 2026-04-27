from __future__ import annotations

import logging

from app.config import settings
from app.models.incident import IncidentBrief
from app.providers.base import NotificationProvider
from app.services import ses as ses_service

logger = logging.getLogger(__name__)


def _compose_subject(incident: IncidentBrief) -> str:
    return f"[Cognis] {incident.severity.upper()} — {incident.incident_id}: {incident.title}"


def _compose_text(incident: IncidentBrief) -> str:
    actions = "\n".join(f"  • {a}" for a in incident.recommended_actions) or "  None"
    runbooks = "\n".join(f"  • {r}" for r in incident.runbook_references) or "  None"
    link = f"{settings.frontend_origin}/incidents/{incident.incident_id}"
    return (
        f"Incident: {incident.incident_id}\n"
        f"Title:    {incident.title}\n"
        f"Severity: {incident.severity}\n"
        f"Service:  {incident.affected_service}\n"
        f"Class:    {incident.failure_class}\n"
        f"Created:  {incident.created_at.isoformat()}\n"
        f"Link:     {link}\n\n"
        f"Summary\n-------\n{incident.summary}\n\n"
        f"Recommended Actions\n-------------------\n{actions}\n\n"
        f"Runbook References\n------------------\n{runbooks}\n"
    )


def _compose_html(incident: IncidentBrief) -> str:
    actions_html = "".join(f"<li>{a}</li>" for a in incident.recommended_actions) or "<li>None</li>"
    runbooks_html = "".join(f"<li>{r}</li>" for r in incident.runbook_references) or "<li>None</li>"
    link = f"{settings.frontend_origin}/incidents/{incident.incident_id}"
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:640px;margin:auto;padding:24px">
  <h2 style="color:#c0392b">[Cognis] {incident.severity.upper()} — {incident.incident_id}</h2>
  <h3>{incident.title}</h3>
  <table>
    <tr><td><strong>Service</strong></td><td>{incident.affected_service}</td></tr>
    <tr><td><strong>Class</strong></td><td>{incident.failure_class}</td></tr>
    <tr><td><strong>Created</strong></td><td>{incident.created_at.isoformat()}</td></tr>
  </table>
  <p><a href="{link}" style="display:inline-block;margin-top:8px;padding:8px 16px;background:#c0392b;color:#fff;text-decoration:none;border-radius:4px">View Incident</a></p>
  <h4>Summary</h4>
  <p>{incident.summary}</p>
  <h4>Recommended Actions</h4>
  <ul>{actions_html}</ul>
  <h4>Runbook References</h4>
  <ul>{runbooks_html}</ul>
</body>
</html>"""


class SESNotificationProvider(NotificationProvider):
    async def send(self, incident: IncidentBrief) -> None:
        subject = _compose_subject(incident)
        body_text = _compose_text(incident)
        body_html = _compose_html(incident)
        to_addresses = [e.strip() for e in settings.ses_to_emails.split(",") if e.strip()]

        if settings.ses_mode == "log":
            print(f"Subject: {subject}\n")
            print(f"Body text:\n{body_text}\n")
            print(f"Body HTML:\n{body_html}\n")
            logger.info(
                "SES log mode — would send email: subject=%s to=%s incident_id=%s",
                subject,
                to_addresses,
                incident.incident_id,
            )
            return

        if not to_addresses:
            logger.warning("SES provider: no recipient addresses configured, skipping send")
            return

        message_id = ses_service.send_email(to_addresses, subject, body_text, body_html)
        logger.info("SES email sent: message_id=%s incident_id=%s", message_id, incident.incident_id)
