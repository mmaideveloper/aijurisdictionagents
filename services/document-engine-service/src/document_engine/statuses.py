from enum import Enum


class DocumentStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    ERROR = "error"
