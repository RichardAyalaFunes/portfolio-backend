"""UpdateContactStage use case -- command DTO.

Richard's one write to the contacts array (see JobApplication.update_contact_stage):
he moves a contact through Not contacted -> Sent -> Replied by hand, from the
dashboard, after he actually sends the message himself.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateContactStageCommand:
    application_id: str
    contact_id: str
    stage: str
