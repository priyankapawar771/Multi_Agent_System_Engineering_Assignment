
import os
import re
import sqlite3
from typing import Any, TypedDict

from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from sqlglot import exp, parse_one

FORBIDDEN_VERBS = ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE")


class AgentState(TypedDict, total=False):
    question: str
    schema_text: str
    sql: str
    validation_error: str
    retry_count: int
    validated: bool
    final_message: str
    trace: list[str]
    simulate_invalid_first_try: bool


def clean_sql_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```sql\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    select_match = re.search(r"(?is)\bselect\b.*", text)
    if select_match:
        text = select_match.group(0).strip()

    if ";" in text:
        text = text.split(";", maxsplit=1)[0].strip()

    return f"{text};"


def get_schema_map(db_path: str) -> dict[str, list[str]]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    tables = [row[0] for row in cursor.fetchall()]

    schema_map: dict[str, list[str]] = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        schema_map[table] = [row[1] for row in cursor.fetchall()]

    conn.close()
    return schema_map


def get_schema_text(db_path: str) -> str:
    database = SQLDatabase.from_uri(f"sqlite:///{db_path}")
    return database.get_table_info()


def check_sql_syntax(sql: str, db_path: str) -> str | None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"EXPLAIN {sql}")
        return None
    except sqlite3.Error as exc:
        message = str(exc)
        lowered = message.lower()
        syntax_indicators = (
            "syntax error",
            "incomplete input",
            "unrecognized token",
            "misuse",
        )
        if any(token in lowered for token in syntax_indicators):
            return f"SQL syntax error: {message}"
        return None
    finally:
        conn.close()


def validate_forbidden_verbs(sql: str) -> str | None:
    upper_sql = sql.upper()
    for verb in FORBIDDEN_VERBS:
        if re.search(rf"\b{verb}\b", upper_sql):
            return (
                f"SQL contains forbidden verb {verb}. "
                f"Only SELECT statements are permitted"
            )

    if not re.match(r"^\s*SELECT\b", sql, flags=re.IGNORECASE):
        return "Only SELECT statements are permitted"

    return None


def get_alias_map(parsed_sql: exp.Expression) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for table in parsed_sql.find_all(exp.Table):
        alias_map[table.alias_or_name] = table.name
    return alias_map


def validate_tables(
    parsed_sql: exp.Expression,
    schema_map: dict[str, list[str]],
) -> str | None:
    available_tables = ", ".join(schema_map.keys())

    for table in parsed_sql.find_all(exp.Table):
        table_name = table.name
        if table_name not in schema_map:
            return (
                f"Table '{table_name}' does not exist. "
                f"Available tables: {available_tables}"
            )

    return None


def validate_columns(
    parsed_sql: exp.Expression,
    schema_map: dict[str, list[str]],
) -> str | None:
    alias_map = get_alias_map(parsed_sql)
    referenced_tables = sorted(set(alias_map.values()))

    for column in parsed_sql.find_all(exp.Column):
        column_name = column.name
        table_alias = column.table

        if column_name == "*":
            continue

        if table_alias:
            resolved_table = alias_map.get(table_alias, table_alias)
            if resolved_table not in schema_map:
                available_tables = ", ".join(schema_map.keys())
                return (
                    f"Table '{resolved_table}' does not exist. "
                    f"Available tables: {available_tables}"
                )

            if column_name not in schema_map[resolved_table]:
                available_columns = ", ".join(schema_map[resolved_table])
                return (
                    f"Column '{column_name}' does not exist in table "
                    f"'{resolved_table}'. Available columns: {available_columns}"
                )
            continue

        matching_tables = [
            table_name
            for table_name in referenced_tables
            if column_name in schema_map[table_name]
        ]

        if len(matching_tables) == 1:
            continue

        if len(matching_tables) == 0:
            if len(referenced_tables) == 1:
                table_name = referenced_tables[0]
                available_columns = ", ".join(schema_map[table_name])
                return (
                    f"Column '{column_name}' does not exist in table "
                    f"'{table_name}'. Available columns: {available_columns}"
                )

            table_list = ", ".join(referenced_tables)
            return (
                f"Column '{column_name}' does not exist in referenced tables: "
                f"{table_list}"
            )

        table_list = ", ".join(matching_tables)
        return (
            f"Column '{column_name}' is ambiguous across tables: {table_list}. "
            f"Qualify it with a table name."
        )

    return None


def validate_sql(sql: str, db_path: str, schema_map: dict[str, list[str]]) -> str | None:
    sql = sql.strip().rstrip(";") + ";"

    syntax_error = check_sql_syntax(sql, db_path)
    if syntax_error:
        return syntax_error

    forbidden_verb_error = validate_forbidden_verbs(sql)
    if forbidden_verb_error:
        return forbidden_verb_error

    try:
        parsed_sql = parse_one(sql, read="sqlite")
    except Exception as exc:
        return f"SQL syntax error: {exc}"

    table_error = validate_tables(parsed_sql, schema_map)
    if table_error:
        return table_error

    column_error = validate_columns(parsed_sql, schema_map)
    if column_error:
        return column_error

    return None


def execute_validated_sql(sql: str, db_path: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    conn.close()
    return rows


def summarize_results(question: str, rows: list[tuple[Any, ...]]) -> str:
    lowered = question.lower()

    if not rows:
        return "The query ran successfully and returned no rows."

    if len(rows) == 1 and len(rows[0]) == 1:
        if "how many" in lowered or "count" in lowered:
            return f"The answer is {rows[0][0]}."
        return f"The result is {rows[0][0]}."

    return f"The query ran successfully and returned {len(rows)} rows."


def format_success_output(sql: str, rows: list[tuple[Any, ...]], summary: str) -> str:
    return (
        "1) Validated SQL query\n"
        "```sql\n"
        f"{sql}\n"
        "```\n\n"
        "2) Raw result rows\n"
        f"{rows}\n\n"
        "3) Plain-English summary\n"
        f"{summary}"
    )


class SQLAnalyticsAgent:
    def __init__(self, db_path: str) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is not set.")

        self.db_path = db_path
        self.schema_text = get_schema_text(db_path)
        self.schema_map = get_schema_map(db_path)
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            temperature=0,
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        graph_builder = StateGraph(AgentState)
        graph_builder.add_node("generate_sql", self.generate_sql_node)
        graph_builder.add_node("validate_sql", self.validate_sql_node)

        graph_builder.add_edge(START, "generate_sql")
        graph_builder.add_edge("generate_sql", "validate_sql")
        graph_builder.add_conditional_edges(
            "validate_sql",
            self.route_after_validation,
            {
                "retry": "generate_sql",
                "end": END,
            },
        )
        app = graph_builder.compile()
        from IPython.display import Image, display

        png_bytes = app.get_graph().draw_mermaid_png()

        with open("logic.png", "wb") as f:
            f.write(png_bytes)

        return app

    def generate_sql_node(self, state: AgentState) -> AgentState:
        question = state["question"]
        schema_text = state["schema_text"]
        validation_error = state.get("validation_error", "")
        retry_count = state.get("retry_count", 0)
        trace = state.get("trace", [])

        if state.get("simulate_invalid_first_try") and retry_count == 0:
            sql = (
                "SELECT t.title, tm.name "
                "FROM tasks t "
                "JOIN team_members tm ON t.assigneed = tm.name "
                "ORDER BY t.id;"
            )
        else:
            system_prompt = (
                "You generate SQLite SQL for a project analytics database. "
                "Return exactly one SQL statement and nothing else. "
                "The output must be a single SELECT statement ending with a semicolon. "
                "Do not generate DDL, DML, PRAGMA, comments, explanations, or markdown. "
                "Use only tables and columns that exist in the provided schema. "
                "When joining tables, fully qualify columns."
            )

            user_prompt = f"""
Question:
{question}

Database schema from SQLDatabase.get_table_info():
{schema_text}

Validator feedback from previous attempt:
{validation_error or "None"}

Rules:
- Return one SELECT statement only.
- Never use DROP, DELETE, UPDATE, INSERT, ALTER, or CREATE.
- If validator feedback is present, fix the SQL precisely.
""".strip()

            response = self.llm.invoke(
                [
                    ("system", system_prompt),
                    ("user", user_prompt),
                ]
            )
            sql = clean_sql_text(response.content)

        new_trace = trace + [f"Attempt {retry_count + 1} SQL: {sql}"]
        return {
            "sql": sql,
            "trace": new_trace,
        }

    def validate_sql_node(self, state: AgentState) -> AgentState:
        sql = state["sql"]
        retry_count = state.get("retry_count", 0)
        trace = state.get("trace", [])

        error_message = validate_sql(sql, self.db_path, self.schema_map)

        if error_message:
            if retry_count >= 2:
                final_trace = trace + [
                    f"Validator error: {error_message}",
                    "Max retries reached.",
                ]
                return {
                    "validated": False,
                    "final_message": (
                        "Unable to generate valid SQL after 2 attempts. "
                        "Please rephrase your question."
                    ),
                    "validation_error": error_message,
                    "trace": final_trace,
                }

            final_trace = trace + [f"Validator error: {error_message}"]
            return {
                "validated": False,
                "validation_error": error_message,
                "retry_count": retry_count + 1,
                "trace": final_trace,
            }

        final_trace = trace + ["Validator status: SQL is valid."]
        return {
            "validated": True,
            "validation_error": "",
            "trace": final_trace,
        }

    @staticmethod
    def route_after_validation(state: AgentState) -> str:
        if state.get("validated"):
            return "end"
        if state.get("final_message"):
            return "end"
        return "retry"

    def answer(
        self,
        question: str,
        verbose: bool = False,
        simulate_invalid_first_try: bool = False,
    ) -> str:
        initial_state: AgentState = {
            "question": question,
            "schema_text": self.schema_text,
            "retry_count": 0,
            "validation_error": "",
            "validated": False,
            "trace": [],
            "simulate_invalid_first_try": simulate_invalid_first_try,
        }

        final_state = self.graph.invoke(initial_state)

        if not final_state.get("validated"):
            if verbose and final_state.get("trace"):
                trace_text = "\n".join(final_state["trace"])
                return f"{trace_text}\n\n{final_state['final_message']}"
            return final_state["final_message"]

        sql = final_state["sql"]
        rows = execute_validated_sql(sql, self.db_path)
        summary = summarize_results(question, rows)
        result = format_success_output(sql, rows, summary)

        if verbose and final_state.get("trace"):
            trace_text = "\n".join(final_state["trace"])
            return f"{trace_text}\n\n{result}"

        return result
