
<!-- filename: README.md -->
# Development Assistant with LangGraph

## Overview
This project implements a ReAct-style development assistant for an engineering team.

The assistant:
- reasons in Thought -> Action -> Observation cycles
- selects the correct tool for the query
- loops until it has enough information to answer
- stops after 6 tool calls for safety
- prints the full reasoning trace to the console

## Tools
1. `story_estimator(description: str) -> str`
   - Returns a story point estimate from: 1, 2, 3, 5, 8, 13
   - Includes a 2-sentence rationale

2. `tech_stack_advisor(requirements: str) -> str`
   - Returns 2 to 3 recommendations
   - Each recommendation has a one-sentence reason

3. `doc_summariser(text: str) -> str`
   - Returns exactly 3 bullet points
   - Each bullet is one sentence

## Setup
1. Create and activate a virtual environment
2. Install dependencies

   `pip install -r requirements.txt`

3. Add your OpenAI API key

   Windows PowerShell:
   `$env:OPENAI_API_KEY="your_key_here"`

   macOS / Linux:
   `export OPENAI_API_KEY="your_key_here"`

4. Optional: choose a model

   `OPENAI_MODEL=gpt-4.1`

## Run
`python main.py`

## Graph / Flow Diagram
```text
START
  |
  v
[reason node]
  |---- final_answer ----> END
  |
  |---- action ----------> [tool node]
                              |
                              v
                         [observation]
                              |
                              v
                         back to reason


You: 'Estimate the effort for adding a CSV export feature to the admin dashboard'
Thought: I still need to call story_estimator before giving the final answer.
Action: story_estimator
Action Input: 'Estimate the effort for adding a CSV export feature to the admin dashboard'
Observation: 3 points — requires backend export logic and dashboard UI changes. The work is moderate and stays inside the existing product area.

Thought: The user has already received an estimate of 3 points for the effort required to add a CSV export feature to the admin dashboard. Since the story_estimator tool has been used, I can provide the final answer without needing to take further action.
Final Answer: The estimated effort for adding a CSV export feature to the admin dashboard is 3 points. This includes backend export logic and dashboard UI changes, and the work is considered moderate within the existing product area.
Assistant: The estimated effort for adding a CSV export feature to the admin dashboard is 3 points. This includes backend export logic and dashboard UI changes, and the work is considered moderate within the existing product area.

You: 'What stack should I use to build a real-time notification system?' 
Thought: I still need to call tech_stack_advisor before giving the final answer.
Action: tech_stack_advisor
Action Input: 'What stack should I use to build a real-time notification system?' 
Observation: FastAPI — lightweight Python framework with strong async support.
Redis — good for pub/sub and fast message delivery.
WebSockets — useful for pushing live updates to clients.

Thought: The user has already received a tech stack suggestion for building a real-time notification system, which includes FastAPI, Redis, and WebSockets. Since the tech_stack_advisor tool has been used, I can provide a final answer based on the previous observations without needing to use any tools again.
Final Answer: To build a real-time notification system, you can use the following stack:
- **FastAPI**: A lightweight Python framework with strong async support, ideal for handling real-time requests.
- **Redis**: Excellent for pub/sub messaging and fast message delivery, making it suitable for real-time notifications.
- **WebSockets**: Useful for pushing live updates to clients, ensuring they receive notifications instantly.
Assistant: To build a real-time notification system, you can use the following stack:
- **FastAPI**: A lightweight Python framework with strong async support, ideal for handling real-time requests.
- **Redis**: Excellent for pub/sub messaging and fast message delivery, making it suitable for real-time notifications.
- **WebSockets**: Useful for pushing live updates to clients, ensuring they receive notifications instantly.

You: 'Summarise this doc: Agent = Model + Harness. LangChain provides create_agent: a minimal, highly configurable harness. The harness is everything around the model loop: the prompt, the tools, and any middleware that shapes behavior. Start with the primitives and compose exactly what your use case needs.
Thought: I still need to call doc_summariser before giving the final answer.
Action: doc_summariser
Action Input: 'Summarise this doc: Agent = Model + Harness. LangChain provides create_agent: a minimal, highly configurable harness. The harness is everything around the model loop: the prompt, the tools, and any middleware that shapes behavior. Start with the primitives and compose exactly what your use case needs.
Observation: - An agent is defined as a combination of a model and a harness in LangChain.  
- The create_agent function offers a minimal and highly configurable harness that encompasses the model loop, including prompts, tools, and middleware.  
- Users can begin with basic components and customize them to fit their specific use cases.

Thought: The user has already used the doc_summariser tool, and I cannot use it again. I need to provide a final answer based on the previous observations.
Final Answer: An agent in LangChain is defined as a combination of a model and a harness. The create_agent function provides a minimal and highly configurable harness that includes the model loop, prompts, tools, and middleware. Users can start with basic components and customize them to meet their specific use cases.
Assistant: An agent in LangChain is defined as a combination of a model and a harness. The create_agent function provides a minimal and highly configurable harness that includes the model loop, prompts, tools, and middleware. Users can start with basic components and customize them to meet their specific use cases.

You: 'I need to add OAuth login — what tech should I use and how much effort will it take?
Thought: I still need to call story_estimator before giving the final answer.
Action: story_estimator
Action Input: 'I need to add OAuth login — what tech should I use and how much effort will it take?
Observation: 5 points — requires authentication flow and session handling. No major new infrastructure appears necessary.

Thought: I still need to call tech_stack_advisor before giving the final answer.
Action: tech_stack_advisor
Action Input: 'I need to add OAuth login — what tech should I use and how much effort will it take?
Observation: FastAPI — clean backend framework for authentication endpoints.
Authlib — simplifies OAuth client and provider flows.
Redis — useful for short-lived session or token state.

Thought: The user has already received estimates for effort and tech stack suggestions. Since both tools have been used, I can provide a final answer based on the previous observations.
Final Answer: To add OAuth login, you can use FastAPI as the backend framework, along with Authlib for handling OAuth flows. Redis can be utilized for managing short-lived sessions or token states. The estimated effort for this implementation is 5 story points, as it requires setting up the authentication flow and session handling, but no major new infrastructure is needed.
Assistant: To add OAuth login, you can use FastAPI as the backend framework, along with Authlib for handling OAuth flows. Redis can be utilized for managing short-lived sessions or token states. The estimated effort for this implementation is 5 story points, as it requires setting up the authentication flow and session handling, but no major new infrastructure is needed.

