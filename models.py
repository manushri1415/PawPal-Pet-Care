from dataclasses import dataclass, field
from typing import List


@dataclass
class Pet:
    """Represents a pet owned by an owner."""
    id: str
    name: str
    type: str
    age: int
    gender: str
    color: str

    def getTasks(self):
        """Retrieve all tasks for this pet."""
        pass

    def getTasksForDay(self, date: str):
        """Retrieve tasks for this pet on a specific date."""
        pass


@dataclass
class Task:
    """Represents a task to be scheduled."""
    id: str
    name: str
    category: str
    petId: str
    duration: int  # in minutes
    priority: str
    frequency: str

    def isRecurring(self) -> bool:
        """Check if this task is recurring."""
        pass

    def canFitInTimeSlot(self, startTime, endTime) -> bool:
        """Check if task can fit in the given time slot."""
        pass

    def getEstimatedEndTime(self, startTime):
        """Get the estimated end time given a start time."""
        pass


@dataclass
class Owner:
    """Represents a pet owner."""
    id: str
    name: str
    email: str
    phoneNumber: str
    availableHoursPerDay: float
    pets: List[Pet] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)

    def addPet(self, pet: Pet):
        """Add a pet to the owner's collection."""
        pass

    def getPets(self) -> List[Pet]:
        """Retrieve all pets owned by this owner."""
        pass

    def addTask(self, task: Task):
        """Add a task to the owner's task list."""
        pass

    def editTask(self, taskId: str, updates: dict):
        """Edit an existing task."""
        pass

    def deleteTask(self, taskId: str):
        """Delete a task from the owner's task list."""
        pass

    def getTasks(self) -> List[Task]:
        """Retrieve all tasks for this owner."""
        pass

    def getAvailableHours(self) -> float:
        """Get available hours per day for scheduling."""
        pass


@dataclass
class DailyPlan:
    """Represents a daily schedule for an owner."""
    date: str
    owner: Owner
    scheduledTasks: List[Task] = field(default_factory=list)
    totalTimeAvailable: float = 0.0
    totalTimeUsed: float = 0.0

    def generateSchedule(self, tasks: List[Task], availableHours: float):
        """Generate a schedule for the given tasks within available hours."""
        pass

    def sortTasksByPriority(self):
        """Sort scheduled tasks by priority."""
        pass

    def fitTasksInAvailableTime(self):
        """Fit as many tasks as possible within available time."""
        pass

    def getFormattedPlan(self) -> str:
        """Get a formatted string representation of the daily plan."""
        pass

    def explainSchedule(self) -> str:
        """Get an explanation of the schedule and its constraints."""
        pass

    def canAddTask(self, task: Task) -> bool:
        """Check if a task can be added to the current schedule."""
        pass