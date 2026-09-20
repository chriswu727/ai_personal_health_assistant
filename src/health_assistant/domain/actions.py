"""What a user confirmed, expressed as an item paired with an external action.

``OperationKind`` lives here rather than beside the operation lifecycle because
approvals must name the action they authorize. A confirmation to create a
calendar event is not a confirmation to cancel one.
"""

from dataclasses import dataclass
from enum import StrEnum

from health_assistant.domain.identifiers import PlanItemId, require_identifier


class OperationKind(StrEnum):
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    CANCEL_EVENT = "cancel_event"


@dataclass(frozen=True, slots=True, order=True)
class ApprovedAction:
    """One plan item paired with the single external action approved for it."""

    item_id: PlanItemId
    kind: OperationKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", require_identifier(self.item_id, "item_id"))
