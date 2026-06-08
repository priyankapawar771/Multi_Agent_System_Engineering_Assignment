
# AutoGen Software Delivery Simulation

## Overview
This project simulates a software delivery team taking a feature from brief to deployment using AutoGen group chat. Five delivery agents collaborate in the live chat: ProductOwner, TechLead, Developer, Tester, and DevOps. A sixth agent, DocumentationWriter, runs after the chat completes and converts the saved transcript into `delivery_report.md`.

## Setup
1. Create a virtual environment
2. Install dependencies from `requirements.txt`
3. Set environment variables:
   - `OPENAI_API_KEY`
   - optional: `OPENAI_MODEL` (default is `gpt-4o-mini`)
4. Run:
   `python main.py`

## Outputs
- `artifacts/transcript.txt`
- `artifacts/delivery_report.md`

## Architecture Diagram
Feature Brief  
→ DeliveryManager kickoff  
→ GroupChatManager (`speaker_selection_method="auto"`, `max_round=15`)  
→ ProductOwner → TechLead → Developer → Tester → TechLead review → DevOps  
→ termination on `DEPLOYMENT_COMPLETE`  
→ DocumentationWriter consumes transcript  
→ `delivery_report.md`

## Why group chat instead of sequential
Group chat is better when the task needs negotiation, challenge, and revision across roles. In this assignment, ProductOwner sets the bar, TechLead proposes the design, Developer implements the core pieces, Tester validates the design, and DevOps waits for upstream confirmation before declaring deployment. That interaction is the point: later agents react to earlier decisions, so the final output is more coherent and traceable. A sequential pipeline is simpler and more predictable, but it often produces stitched-together artifacts because each step only sees the original prompt or a narrow handoff. Group chat adds overhead, token cost, and some speaker-selection variability, yet it better reflects real delivery work where design, build, test, and release decisions influence one another. For this scenario, group chat is the stronger choice because the marking rubric rewards cross-agent collaboration, visible review loops, and outputs grounded in the shared transcript.

## Submission Checklist
- Commit `artifacts/transcript.txt`
- Commit `artifacts/delivery_report.md`
- Keep all 6 agent system messages distinct
- Ensure TechLead's architecture is visible in Developer and Tester outputs
- Include this README in the repo
