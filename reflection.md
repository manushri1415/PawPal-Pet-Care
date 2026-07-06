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

Yes, When I completed the recurring tasks, I didn't think too much about the "end repeat date". I had to re-inplement it to ensure it works.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

The scheduler looks at work hours, task duration, priority, and any preferred time. Tasks with a fixed time (like medication) get scheduled first, even outside work hours, since those times can't move. Everything else fills the remaining time slots by priority, highest first. Time and priority matter most because pet care has real deadlines and clear urgency, while things like notes are just informational.

**b. Tradeoffs**

The main tradeoff: the scheduler fills the day by priority order and doesn't rearrange tasks to fit more in. A high-priority task always gets a slot first, even if a different order could've packed the day tighter.

This is fine because owners only have a handful of tasks a day, so squeezing in every last one doesn't matter much. What matters is that urgent things like feeding come first. If a task doesn't fit, the owner can just skip it that day instead of the scheduler rearranging everything.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

I used Claude (via Claude Code) one feature at a time instead of asking for the whole app at once. First it turned my design into skeleton classes, then filled in the main logic, then in later passes added edge-case handling, repeating tasks, and conflict checking, and finally connected everything to the app screen. The prompts that worked best were specific, like "check for conflicts across all pets, not just one," because there was a clear right answer to check against instead of something vague like "make it smarter." 

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

I had a hard time with the UI of the website as I am really new to streamlit. So I had to initially give AI the freedom for the UI and focus on the backend. But soon as more functionalities were implemented I had to restructure the whole UI based on requirements. 

AI seemed to not get UI structure well unlike backend features. I then had to make a small sketch of how I wanted the UI section to look like and pasted it to AI to recreate it. 

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

I tested things like: marking tasks done, adding tasks, setting work hours, building the daily schedule (time slots, breaks, priority order, fixed vs. flexible times), sorting tasks by time, catching schedule conflicts (overlapping, back-to-back, one inside another, across different pets), repeating tasks generating correctly, and the app screen itself. These mattered because small mistakes in this kind of logic can look fine but quietly give a wrong answer — like flagging back-to-back tasks as a conflict when they're not, or crashing on certain dates.

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

I feel good about the core scheduling, sorting, and conflict-checking, since it's backed by both normal and tricky test cases. I'm less sure about how well it handles a very busy day with lots of fixed-time and flexible tasks competing for the same open spots, the current approach just takes the first open slot that works, which isn't necessarily the best fit. With more time I'd add a way to tell the owner when a task couldn't be scheduled at all, instead of it just quietly disappearing, and make the scheduler smarter about filling gaps between tasks, not just after them.

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

I'm most happy with the conflict-checking and repeating-task features, since I pushed past just getting them working on the easy case and actually tested the ways they could quietly break, like back-to-back tasks, tasks fully inside other tasks, and month-end date issues. Those are bugs that wouldn't show up in a quick demo but would show up after real, ongoing use.

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

I'd improve The UI. I also wanted to complete the stretch features but swamped with work and didn't get the chance to fully embrace the problem.

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?

The biggest lesson was that AI-written code is only as trustworthy as the tests I write for it. Some bugs looked totally fine just reading the code and only showed up once I tested a specific edge case. Treating AI output as a first draft to check, rather than a finished answer, mattered more than trying to write the perfect prompt upfront.
