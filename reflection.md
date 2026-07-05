# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

Core actions:
    - Let a user enter basic owner + pet info [Sign up page]
    - Let a user add/edit tasks (duration + priority at minimum) 
    - Generate a daily schedule/plan based on constraints and priorities
    - Display the plan clearly (and ideally explain the reasoning)
    - Include tests for the most important scheduling behaviors

- Briefly describe your initial UML design.

Initial design contained just owner, pet and tasks. Based on the core actions I then had to add DailyPlan (which will be generated for a day)
- What classes did you include, and what responsibilities did you assign to each?

Main objects:

Owner:
    Attributes:
        id (unique)
        name
        email
        phone number
        availableHoursPerDay (time constraint)
    Methods:
        addPet(pet)
        getPets()
        addTask(task)
        editTask(taskId, updates)
        deleteTask(taskId)
        getTasks()
        getAvailableHours()

Pet:
    Attributes:
        id
        name
        type (cat/dog/etc)
        age
        gender
        color
    Methods:
        getTasks()
        getTasksForDay(date)

Task:
    Attributes:
        id
        name
        duration (minutes)
        priority (high/medium/low)
        category (walk, feeding, medication, grooming, enrichment, vet, etc.)
        frequency (once, daily, weekly, etc.)
        petId (which pet this task is for)
    Methods:
        isRecurring()
        canFitInTimeSlot(startTime, endTime)
        getEstimatedEndTime(startTime)

DailyPlan (or Schedule):
    Attributes:
        date
        owner
        scheduledTasks (ordered list of tasks)
        totalTimeAvailable
        totalTimeUsed
    Methods:
        generateSchedule(tasks, availableHours)
        sortTasksByPriority()
        fitTasksInAvailableTime()
        getFormattedPlan()
        explainSchedule() (explain why tasks are scheduled in this order)
        canAddTask(task)

**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

Enum instead of a string for categories like priotities and gender

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

The scheduler makes one big choice: it schedules tasks in order of importance and never changes them. So if you have a high-priority task, it gets scheduled first, and medium-priority tasks fit in after—even if moving things around might squeeze more tasks in total.

Owners usually only have 5-10 tasks a day, so speed doesn't matter. Plus, important things like feeding pets should really come first anyway. If something doesn't fit in the schedule, the owner can just decide to do fewer tasks that day instead of asking the scheduler to juggle everything around.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
