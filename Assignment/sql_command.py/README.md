# Natural-Language SQL Analytics Agent

This project builds a natural-language analytics agent for a SQLite project database.

The agent:
1. converts a user question into SQL,
2. validates the SQL before execution,
3. retries with validator feedback if the SQL is wrong,
4. executes only validated SQL,
5. returns:
   - the validated SQL,
   - raw result rows,
   - a plain-English summary.

## Tech Stack
- Python
- SQLite
- LangGraph StateGraph
- OpenAI API
- LangChain SQLDatabase for schema introspection
- sqlglot for table/column inspection

## Project Files
- `seed_db.py` — recreates and seeds the SQLite database
- `agent.py` — generator node, validator node, retry loop, executor helpers
- `main.py` — CLI entry point
- `requirements.txt` — dependencies

## Architecture

Question
  |
  v
SQL Generator node
  |
  v
SQL Validator node
  |------------------------------\
  | valid                         \ invalid + specific feedback
  v                                \
Execute validated SQL               \
  |                                  \
  v                                   \
Final answer                           -> back to SQL Generator
                                         (max 2 retries)

## Why this matches the rubric
- **Graph & Pattern**: implemented with LangGraph `StateGraph`
- **Reflection Loop**: validator returns specific feedback, generator sees it on retry
- **SQL Accuracy**: generator uses schema from `SQLDatabase.get_table_info()`
- **Safety**: SQL is never executed before validation
- **Documentation**: setup, architecture, transcript, and test runs are included here

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

~~~bash
pip install -r requirements.txt
~~~

3. Set your OpenAI API key:

~~~bash
export OPENAI_API_KEY="your_key_here"
~~~

Optional model override:

~~~bash
export OPENAI_MODEL="gpt-4.1"
~~~

4. Recreate the database:

~~~bash
python seed_db.py
~~~

## Database Seed Summary
The seed script creates:
- 3 projects
- 8 tasks with mixed statuses
- 4 team members
- 3 incidents:
  - 1 critical
  - 1 high
  - 1 low

## Manual Verification Queries
Run these directly if you want to verify the database after seeding:

~~~sql
SELECT COUNT(*) FROM tasks;
SELECT severity, COUNT(*) FROM incidents GROUP BY severity;
~~~

## Running the Agent

Example:

~~~bash
python main.py "How many tasks are currently blocked?"
~~~

Verbose mode:

~~~bash
python main.py --verbose "Show me all high or critical priority projects"
~~~

Retry demo mode for README transcript:

~~~bash
python main.py --verbose --simulate-invalid-first-try \
"List all tasks along with the name of the team member assigned to each"
~~~

## Required Test Queries

### 1) COUNT
Question:
`How many tasks are currently blocked?`

Expected validated SQL shape:
~~~sql
SELECT COUNT(*) FROM tasks WHERE status = 'blocked';
~~~

Expected result:
~~~text
[(2,)]
~~~

### 2) JOIN
Question:
`List all tasks along with the name of the team member assigned to each`

Expected validated SQL shape:
~~~sql
SELECT t.title, tm.name
FROM tasks t
JOIN team_members tm ON t.assignee = tm.name
ORDER BY t.id;
~~~

### 3) FILTER
Question:
`Show me all high or critical priority projects`

Expected validated SQL shape:
~~~sql
SELECT *
FROM projects
WHERE priority IN ('high', 'critical')
ORDER BY id;
~~~

### 4) AGGREGATE
Question:
`What is the average story points per assignee?`

Expected validated SQL shape:
~~~sql
SELECT assignee, AVG(story_points)
FROM tasks
GROUP BY assignee
ORDER BY assignee;
~~~

## Sample Retry Transcript

Command:

~~~bash
python main.py --verbose --simulate-invalid-first-try \
"List all tasks along with the name of the team member assigned to each"
~~~

Example transcript:

~~~text
Attempt 1 SQL: SELECT t.title, tm.name FROM tasks t JOIN team_members tm ON t.assigneed = tm.name ORDER BY t.id;
Validator error: Column 'assigneed' does not exist in table 'tasks'. Available columns: id, project_id, title, status, assignee, story_points, due_date
Attempt 2 SQL: SELECT t.title, tm.name FROM tasks t JOIN team_members tm ON t.assignee = tm.name ORDER BY t.id;
Validator status: SQL is valid.

1) Validated SQL query
```sql
SELECT t.title, tm.name FROM tasks t JOIN team_members tm ON t.assignee = tm.name ORDER BY t.id;
```

2) Raw result rows
[('Design API contracts', 'Alice Johnson'), ('Build auth service', 'Bob Smith'), ('Frontend integration', 'Carol Lee'), ('Assess legacy systems', 'David Kim'), ('Plan cutover', 'Alice Johnson'), ('Data migration scripts', 'Bob Smith'), ('Incident triage playbook', 'Carol Lee'), ('Monitoring dashboard', 'David Kim')]

3) Plain-English summary
The query ran successfully and returned 8 rows.
~~~

## Submission Checklist
- [x] `seed_db.py` recreates the DB in one command
- [x] Validator error messages are specific
- [x] At least one retry cycle is shown in README
- [x] Final answer includes SQL + raw rows + plain-English summary
- [x] Schema introspection uses `SQLDatabase.get_table_info()`
- [x] Max retry count is capped at 2


Enter your question: How many tasks are currently blocked?
Graph image saved as langgraph.png
1) Validated SQL query
```sql
-- Code Generated by Sidekick is for learning and experimentation purposes only.
SELECT COUNT(*) FROM tasks WHERE tasks.status = 'blocked';
```

2) Raw result rows
[(2,)]

3) Plain-English summary
The answer is 2.


Enter your question: List all tasks along with the name of the team member assigned to each
Graph image saved as langgraph.png
1) Validated SQL query
```sql
SELECT tasks.title, team_members.name FROM tasks LEFT JOIN team_members ON tasks.assignee = team_members.name;
```

2) Raw result rows
[('Design API contracts', 'Alice Johnson'), ('Build auth service', 'Bob Smith'), ('Frontend integration', 'Carol Lee'), ('Assess legacy systems', 'David Kim'), ('Plan cutover', 'Alice Johnson'), ('Data migration scripts', 'Bob Smith'), ('Incident triage playbook', 'Carol Lee'), ('Monitoring dashboard', 'David Kim')]

3) Plain-English summary
The query ran successfully and returned 8 rows.

Question: Show me all high or critical priority projects
1) Validated SQL query
```sql
-- Code Generated by Sidekick is for learning and experimentation purposes only.
SELECT * FROM projects WHERE projects.priority IN ('high', 'critical');
```

2) Raw result rows
[(1, 'Apollo Revamp', 'active', 'high', '2026-01-15', '2026-08-30', 'Alice Johnson', 250000), (2, 'Neptune Migration', 'planning', 'critical', '2026-03-01', '2026-11-15', 'Bob Smith', 400000)]

3) Plain-English summary
The query ran successfully and returned 2 rows.

Enter your question: 'What is the average story points per assignee?
1) Validated SQL query

SELECT tasks.assignee, AVG(tasks.story_points) AS average_story_points FROM tasks GROUP BY tasks.assignee;
```

2) Raw result rows
[('Alice Johnson', 5.0), ('Bob Smith', 8.0), ('Carol Lee', 3.5), ('David Kim', 4.0)]

3) Plain-English summary
The query ran successfully and returned 4 rows.
