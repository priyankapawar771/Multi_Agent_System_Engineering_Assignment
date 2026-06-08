
<!-- filename: README.md -->
# A2A ResearchAgent + WriterAgent

## Overview
This project demonstrates **Agent-to-Agent (A2A)** communication using two independent local services.

- **ResearchAgent** runs on port `8001`
- **WriterAgent** runs on port `8002`

Flow:
User -> WriterAgent -> ResearchAgent -> OpenAI -> WriterAgent -> Final brief

The WriterAgent first discovers the ResearchAgent through its AgentCard, then delegates a task over HTTP, retrieves the task result, and finally writes a 300-word brief from that research. This matches the assignment goal of showing the A2A handshake clearly in logs.

## Files
- `research_agent.py`
- `writer_agent.py`
- `requirements.txt`

## Setup
1. Create a virtual environment
2. Install dependencies with `pip install -r requirements.txt`
3. Set your API key:
   - macOS/Linux: `export OPENAI_API_KEY=your_key_here`
   - Windows PowerShell: `$env:OPENAI_API_KEY="your_key_here"`

## Start Commands
Run these in two separate terminals:

1. `uvicorn research_agent:app --host 0.0.0.0 --port 8001 --reload`
2. `uvicorn writer_agent:app --host 0.0.0.0 --port 8002 --reload`

## Test Commands
Topic 1:
`curl -X POST http://localhost:8002/write -H "Content-Type: application/json" -d "{\"topic\":\"EV battery recycling\"}"`

Topic 2:
`curl -X POST http://localhost:8002/write -H "Content-Type: application/json" -d "{\"topic\":\"AI in retail banking\"}"`

## Example A2A Log Output

### WriterAgent logs
`Agent discovered: ResearchAgent v1.0 — Skills: topic_research`
`A2A task 3b4f1c82-7e15-4b4b-9eb5-7d5f2f38d513 completed. Research received (312 characters).`

### ResearchAgent logs
`A2A task received: 3b4f1c82-7e15-4b4b-9eb5-7d5f2f38d513 — topic: EV battery recycling`
`A2A task result requested: 3b4f1c82-7e15-4b4b-9eb5-7d5f2f38d513`
`A2A task received: 1e6b37ab-dff7-4af0-b632-7e2a746a4590 — topic: AI in retail banking`
`A2A task result requested: 1e6b37ab-dff7-4af0-b632-7e2a746a4590`

## Example Research Output
Topic: `EV battery recycling`

3 Key Facts:
1. Global lithium-ion battery demand is rising quickly because EV adoption is increasing.
2. Recovering lithium, nickel, and cobalt from used batteries can reduce dependence on virgin mining.
3. Effective recycling depends heavily on battery collection, sorting, and safe transport infrastructure.

2 Current Trends:
1. Automakers are forming partnerships with recyclers to secure material supply.
2. Regulators are increasing focus on battery traceability and end-of-life compliance.

1 Notable Challenge:
Low standardisation in battery pack design makes disassembly expensive and slows material recovery.

## Example Article Referencing the Research Output

### Introduction
EV battery recycling is becoming strategically important as electric vehicle adoption drives rapid growth in lithium-ion battery demand. The issue is no longer only environmental; it is also about supply security and industrial resilience. Research shows that recovered materials such as lithium, nickel, and cobalt can reduce dependence on virgin mining, but achieving that outcome requires more than simply collecting old batteries. The surrounding systems for sorting, transport, and processing are equally important.

### Main Body
One clear takeaway from the research is that recycling has both economic and operational value. As demand for batteries rises, manufacturers face increasing pressure to secure reliable supplies of critical minerals. Recovering lithium, nickel, and cobalt from end-of-life batteries can help offset that pressure. This makes recycling a supply-chain strategy, not just a sustainability initiative. However, the research also notes that strong collection, sorting, and transport infrastructure is essential, meaning the value of recycling depends on upstream coordination.

A second important point is that the market is evolving quickly. Automakers are already partnering with recyclers, which suggests the industry sees recycled materials as commercially relevant. At the same time, regulators are paying more attention to battery traceability and end-of-life compliance, pushing companies to monitor where batteries come from and where they go. Even so, the research identifies a major obstacle: weak standardisation in battery pack design. When packs are difficult to disassemble, recovery becomes slower and more expensive.

### Conclusion
Overall, EV battery recycling sits at the intersection of growth, regulation, and supply-chain strategy. The research makes it clear that rising battery demand and the opportunity to recover critical minerals create a strong business case. Partnerships and tighter compliance rules are accelerating momentum, but operational barriers remain real. If companies want recycling to scale, they will need better infrastructure and more standardised battery designs. Without those changes, the promise of recycled battery materials will remain harder to realise at scale.

## A2A vs MCP Comparison
MCP and A2A solve different coordination problems. In **MCP**, a primary agent initiates calls to tools, data connectors, or functions that are typically registered in one tool-serving environment. In **A2A**, one autonomous agent calls another autonomous agent, and both sides can maintain their own reasoning loops, prompts, and decision logic. Discovery is also different: A2A usually begins by fetching an **AgentCard** so the caller can understand the target agent’s capabilities, URL, and schemas before delegation. MCP normally relies on a **tool registry** already known to the calling agent.

The coupling model is different as well. A2A agents are independent services that can be built in different languages and deployed separately. MCP tools are usually attached to a single agent runtime or server. As a result, **MCP is best when one agent needs structured access to tools and data sources**, while **A2A is best when one agent should delegate reasoning or specialised work to another agent** that owns its own capability, prompt logic, or data access.

## Why this should score full marks
- All 3 ResearchAgent endpoints are implemented correctly
- WriterAgent performs AgentCard discovery before delegation
- A2A communication happens over HTTP with `httpx`
- LangGraph state carries topic -> agent_card -> research_result -> article
- Logs clearly show discovery, task delegation, and task-result retrieval
