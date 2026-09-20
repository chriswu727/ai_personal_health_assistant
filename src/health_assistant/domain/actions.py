"""What a user confirmed, expressed as an item, an action, and its target.

``OperationKind`` lives here rather than beside the operation lifecycle because
approvals must name the action they authorize. A confirmation to create a
calendar event is not a confirmation to cancel one, and a confirmation to undo
one particular write is not a confirmation to undo a different one.
"""

from dataclasses import dataclass
from enum import StrEnum

from health_assistant.domain.identifiers import OperationId, PlanItemId, require_identifier


class OperationKind(StrEnum):
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    CANCEL_EVENT = "cancel_event"


@dataclass(frozen=True, slots=True)
class ApprovedAction:
    """One plan item, the external action approved for it, and that action's target.

    ``compensates`` names the earlier operation whose external write this action
    undoes. It is part of what the user approved: agreeing to cancel the event
    created by one write says nothing about cancelling a different one.
    """

    item_id: PlanItemId
    kind: OperationKind
    compensates: OperationId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", require_identifier(self.item_id, "item_id"))
        if self.compensates is not None:
            object.__setattr__(
                self, "compensates", require_identifier(self.compensates, "compensates")
            )


def action_sort_key(action: ApprovedAction) -> tuple[str, str, str]:
    """Return a total order that tolerates an absent compensation target."""
    return (action.item_id, str(action.kind), action.compensates or "")
