# **1. Coordinator Agent (`CoordinatorState`)**

**Role:** *The Manager* — Receives the user request, breaks it into tasks, delegates, and monitors execution.

| **State**      | **When It Is Used**                                                                        | **Meaning**                                             |
| -------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| **planning**   | Immediately upon receiving the POST request. The system is deciding what tasks are needed. | “I'm thinking about how to break this down.”            |
| **assigned**   | After planning is done. Tasks have been generated but not yet delivered to the Delegator.  | “I have a plan (a list of tasks), ready to send.”       |
| **monitoring** | After sending tasks to the Delegator. The Coordinator listens to Redis for updates.        | “I've handed off the work. I'm watching the dashboard.” |
| **completed**  | When all tasks have finished (success or failure).                                         | “The entire job is finished.”                           |

---

# **2. Delegator Agent (`DelegatorState`)**

**Role:** *The Dispatcher* — Accepts task bundles from the Coordinator and assigns tasks to Worker agents.

| **State**      | **When It Is Used**                                         | **Meaning**                                       |
| -------------- | ----------------------------------------------------------- | ------------------------------------------------- |
| **idle**       | Default state. Waiting for new work from the Coordinator.   | “I'm waiting for a new job.”                      |
| **accepting**  | When receiving the task list from the Coordinator via HTTP. | “I'm grabbing the list of tasks you gave me.”     |
| **delegating** | When routing tasks and calling the appropriate Workers.     | “I'm handing out assignments to the workers.”     |
| **monitoring** | When waiting for all Workers to finish and report status.   | “I'm waiting for my team to finish.”              |
| **completed**  | When all tasks (from all workers) have finished.            | “My team is done. Reporting back to Coordinator.” |

---

# **3. Worker Agent (`WorkerState`)**

**Role:** *The Employee* — Executes a single assigned task step-by-step.

| **State**       | **When It Is Used**                                      | **Meaning**                           |
| --------------- | -------------------------------------------------------- | ------------------------------------- |
| **idle**        | Default state. Waiting for a new task from Delegator.    | “I'm ready to work.”                  |
| **started**     | When the Worker receives a task via HTTP.                | “I got the ticket. I'm starting now.” |
| **in_progress** | While executing the task step-by-step (e.g., Step 1/3…). | “I'm busy working on it.”             |
| **completed**   | When all steps finish successfully.                      | “I'm finished. Here is the result.”   |
| **failed**      | When an exception or error occurs.                       | “I crashed. I can't finish this.”     |

---

# **Overall System Flow (Summary)**

1. **Coordinator → planning**
   “User wants a website? Okay, I need a *frontend task* and a *backend task*.”

2. **Coordinator → monitoring → Delegator (accepting)**
   “Here are the tasks, Delegator.”

3. **Delegator → delegating**
   “Worker A, you do frontend. Worker B, you do backend.”

4. **Workers → started → in_progress**
   “On it!”

5. **Workers → completed**
   “Done!”

6. **Delegator → monitoring → completed**
   “All workers are done.”

7. **Coordinator → completed**
   “The request is finished.”

